"""Demand-driven HTTP range cache for DefeatBeta's versioned Parquet dataset."""

import hashlib
import json
import os
import re
import tempfile
import time
from collections import OrderedDict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable, Optional
from urllib.parse import urlsplit

import fsspec
import httpx


_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
_BLOCK_DIGEST_BYTES = hashlib.sha256().digest_size


class DatasetCacheFileSystem(fsspec.AbstractFileSystem):
    """Expose versioned remote files to DuckDB without a DuckDB binary extension.

    Each HTTP range is aligned to a configurable block size. The disk cache
    contains only blocks that DuckDB requested; it never materializes the
    entire remote object. A unique temporary file is renamed into place only
    after a complete, validated response has been received.
    """

    protocol = "defeatbeta"
    root_marker = ""

    def __init__(
        self,
        directory: str,
        version: str,
        resolve: Callable[[str, bool], str],
        http_proxy: Optional[str] = None,
        block_size: int = 1024 * 1024,
        max_disk_bytes: int = 1024 * 1024 * 1024,
        max_memory_blocks: int = 64,
        workers: int = 3,
        timeout: float = 60,
        http_client=None,
        **kwargs,
    ):
        super().__init__(skip_instance_cache=True, **kwargs)
        if (not version or min(block_size, max_disk_bytes, workers) <= 0
                or max_memory_blocks < 0):
            raise ValueError("Dataset cache version and limits must be positive")
        if max_disk_bytes < block_size + _BLOCK_DIGEST_BYTES:
            raise ValueError("Disk cache limit must hold at least one block size")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.version = version
        self.resolve = resolve
        self.block_size = block_size
        self.max_disk_bytes = max_disk_bytes
        self.max_memory_blocks = max_memory_blocks
        self._client = http_client if http_client is not None else httpx.Client(
            http2=True,
            proxy=http_proxy or None,
            trust_env=http_proxy is None,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=workers,
                max_keepalive_connections=workers,
                keepalive_expiry=120,
            ),
        )
        self._owns_client = http_client is None
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._files = {}
        self._metadata_locks = {}
        self._pending = {}
        self._sizes = {}
        self._memory_blocks = OrderedDict()
        self._guard = Lock()
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "downloaded_bytes": 0,
            "range_requests": 0,
            "range_seconds": 0.0,
        }
        self._range_events = deque(maxlen=1024)
        self._range_sequence = 0

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        if self._owns_client:
            self._client.close()

    def metrics(self):
        with self._guard:
            return dict(self._metrics)

    def range_event_sequence(self):
        with self._guard:
            return self._range_sequence

    def range_events(self, since=0):
        with self._guard:
            return [event for event in self._range_events
                    if event["sequence"] > since]

    def register(self, resolve_url: str) -> str:
        """Return a stable virtual path for a pinned dataset URL."""
        parts = urlsplit(resolve_url)
        if (parts.scheme != "https" or parts.hostname != "huggingface.co"
                or not parts.path.startswith(
                    "/datasets/defeatbeta/yahoo-finance-data/resolve/"
                ) or not parts.path.endswith((".parquet", ".json"))
                or parts.query or parts.fragment):
            raise ValueError("Only pinned DefeatBeta data URLs can be cached")
        key = hashlib.sha256(f"{self.version}\n{resolve_url}".encode()).hexdigest()
        with self._guard:
            self._files[key] = resolve_url
        return f"{self.protocol}://{key}/{Path(parts.path).name}"

    def _key_and_url(self, path):
        stripped = self._strip_protocol(str(path)).lstrip("/")
        key = stripped.split("/", 1)[0]
        with self._guard:
            url = self._files.get(key)
        if url is None:
            raise FileNotFoundError("Unknown DefeatBeta dataset cache path")
        return key, url

    def _object_dir(self, key):
        directory = self.directory / key
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _check_response(response, start, end, expected_total=None):
        match = _CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
        if response.status_code != 206 or match is None:
            raise ValueError("Remote server did not honor the requested range")
        actual_start, actual_end, total = map(int, match.groups())
        if (actual_start, actual_end) != (start, end) or total <= end:
            raise ValueError("Remote server returned an inconsistent range")
        if expected_total is not None and total != expected_total:
            raise ValueError("Remote file changed during the range request")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("Remote server encoded a byte-range response")
        if len(response.content) != end - start + 1:
            raise ValueError("Remote server returned a truncated range")
        return total

    def _request_range(self, url, start, end, expected_total=None):
        started = time.perf_counter()
        for refresh in (False, True):
            resolved = self.resolve(url, refresh)
            signed_url = resolved[0] if isinstance(resolved, tuple) else resolved
            response = self._client.get(
                signed_url,
                headers={"Range": f"bytes={start}-{end}",
                         "Accept-Encoding": "identity"},
            )
            if response.status_code in (401, 403) and not refresh:
                continue
            total = self._check_response(response, start, end, expected_total)
            with self._guard:
                self._metrics["range_requests"] += 1
                self._metrics["downloaded_bytes"] += len(response.content)
                self._metrics["range_seconds"] += time.perf_counter() - started
                self._range_sequence += 1
                self._range_events.append({
                    "sequence": self._range_sequence,
                    "start": start,
                    "end": end,
                    "bytes": len(response.content),
                    "seconds": time.perf_counter() - started,
                    "http_version": response.http_version,
                })
            return response.content, total
        raise RuntimeError("Signed dataset URL expired after refresh")

    def _get_size(self, key, url):
        with self._guard:
            cached_size = self._sizes.get(key)
        if cached_size is not None:
            return cached_size
        metadata = self._object_dir(key) / "size.json"
        try:
            size = json.loads(metadata.read_text(encoding="utf-8"))["size"]
            if isinstance(size, int) and size > 0:
                with self._guard:
                    self._sizes[key] = size
                return size
        except (OSError, ValueError, KeyError, TypeError):
            pass
        with self._guard:
            lock = self._metadata_locks.setdefault(key, Lock())
        with lock:
            try:
                size = json.loads(metadata.read_text(encoding="utf-8"))["size"]
                if isinstance(size, int) and size > 0:
                    with self._guard:
                        self._sizes[key] = size
                    return size
            except (OSError, ValueError, KeyError, TypeError):
                pass
            resolved = self.resolve(url, False)
            size = resolved[1] if isinstance(resolved, tuple) else None
            if not isinstance(size, int) or size <= 0:
                _, size = self._request_range(url, 0, 0)
            try:
                self._atomic_write(metadata, json.dumps({"size": size}).encode())
            except OSError:
                try:
                    existing_size = json.loads(
                        metadata.read_text(encoding="utf-8")
                    )["size"]
                except (OSError, ValueError, KeyError, TypeError):
                    raise
                if existing_size != size:
                    raise
            with self._guard:
                self._sizes[key] = size
            return size

    @staticmethod
    def _atomic_write(target: Path, content: bytes):
        descriptor, name = tempfile.mkstemp(prefix=".partial-", dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def info(self, path, **kwargs):
        key, url = self._key_and_url(path)
        return {"name": path, "size": self._get_size(key, url), "type": "file"}

    def ls(self, path, detail=True, **kwargs):
        entry = self.info(path)
        return [entry] if detail else [entry["name"]]

    def glob(self, path, **kwargs):
        try:
            self._key_and_url(path)
            return [path]
        except FileNotFoundError:
            return []

    def modified(self, path):
        return datetime.fromtimestamp(0, timezone.utc)

    def created(self, path):
        return self.modified(path)

    def _open(self, path, mode="rb", **kwargs):
        if mode != "rb":
            raise ValueError("Dataset cache filesystem is read-only")
        return fsspec.spec.AbstractBufferedFile(
            self, path, mode="rb", block_size=self.block_size,
            cache_type="none", size=self.info(path)["size"],
        )

    def _block_path(self, key, start, length):
        return self._object_dir(key) / f"{start}-{length}.block"

    def _read_block(self, path, length):
        try:
            stored = path.read_bytes()
            digest, content = stored[:_BLOCK_DIGEST_BYTES], stored[_BLOCK_DIGEST_BYTES:]
            if (len(content) == length and len(digest) == _BLOCK_DIGEST_BYTES
                    and hashlib.sha256(content).digest() == digest):
                try:
                    os.utime(path, None)
                except OSError:
                    pass
                with self._guard:
                    self._metrics["cache_hits"] += 1
                return content
        except OSError:
            pass
        return None

    def _memory_get(self, cache_key):
        with self._guard:
            content = self._memory_blocks.pop(cache_key, None)
            if content is not None:
                self._memory_blocks[cache_key] = content
                self._metrics["cache_hits"] += 1
            return content

    def _memory_put(self, cache_key, content):
        if self.max_memory_blocks == 0:
            return
        with self._guard:
            self._memory_blocks.pop(cache_key, None)
            self._memory_blocks[cache_key] = content
            while len(self._memory_blocks) > self.max_memory_blocks:
                self._memory_blocks.popitem(last=False)

    def _fetch_block(self, key, url, start, length, total):
        cache_key = (key, start, length)
        in_memory = self._memory_get(cache_key)
        if in_memory is not None:
            return in_memory
        target = self._block_path(key, start, length)
        existing = self._read_block(target, length)
        if existing is not None:
            self._memory_put(cache_key, existing)
            return existing
        content, _ = self._request_range(url, start, start + length - 1, total)
        try:
            self._atomic_write(target, hashlib.sha256(content).digest() + content)
        except OSError:
            existing = self._read_block(target, length)
            if existing is None:
                raise
            self._memory_put(cache_key, existing)
            return existing
        self._memory_put(cache_key, content)
        self._prune(target)
        return content

    def _prune(self, keep):
        entries = []
        for path in self.directory.rglob("*.block"):
            try:
                stat = path.stat()
                entries.append((stat.st_mtime_ns, stat.st_size, path))
            except OSError:
                continue
        total = sum(size for _, size, _ in entries)
        for _, size, path in sorted(entries):
            if total <= self.max_disk_bytes:
                break
            if path == keep:
                continue
            try:
                path.unlink()
                total -= size
            except OSError:
                # Windows can reject removal while another reader holds the file.
                continue

    def _block(self, key, url, start, length, total):
        cache_key = (key, start, length)
        in_memory = self._memory_get(cache_key)
        if in_memory is not None:
            return in_memory
        path = self._block_path(key, start, length)
        content = self._read_block(path, length)
        if content is not None:
            self._memory_put(cache_key, content)
            return content
        pending_key = (key, start, length)
        scheduled = False
        with self._guard:
            future = self._pending.get(pending_key)
            if future is None:
                self._metrics["cache_misses"] += 1
                future = self._executor.submit(
                    self._fetch_block, key, url, start, length, total
                )
                self._pending[pending_key] = future
                scheduled = True
        if scheduled:
            future.add_done_callback(
                lambda completed: self._forget_pending(pending_key, completed)
            )
        return future

    def _forget_pending(self, pending_key, future):
        with self._guard:
            if self._pending.get(pending_key) is future:
                self._pending.pop(pending_key, None)

    def prefetch(self, path, first_blocks=2, tail=True):
        """Start query-specific blocks concurrently without waiting for them."""
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        last = ((total - 1) // self.block_size) * self.block_size
        offsets = {index * self.block_size for index in range(first_blocks)
                   if index * self.block_size < total}
        if tail:
            offsets.add(last)
        for start in sorted(offsets):
            length = min(self.block_size, total - start)
            target = self._block_path(key, start, length)
            try:
                if target.stat().st_size == length + _BLOCK_DIGEST_BYTES:
                    continue
            except OSError:
                pass
            self._block(key, url, start, length, total)

    def cat_file(self, path, start=None, end=None, **kwargs):
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        start = 0 if start is None else max(0, start)
        end = total if end is None else min(end, total)
        if end <= start:
            return b""
        parts = []
        for offset in range((start // self.block_size) * self.block_size,
                            end, self.block_size):
            length = min(self.block_size, total - offset)
            parts.append((offset, self._block(key, url, offset, length, total)))
        result = []
        for offset, value in parts:
            if isinstance(value, Future):
                pending_key = (key, offset, min(self.block_size, total - offset))
                try:
                    content = value.result()
                finally:
                    with self._guard:
                        if self._pending.get(pending_key) is value:
                            self._pending.pop(pending_key, None)
            else:
                content = value
            result.append(content[max(0, start - offset):min(len(content), end - offset)])
        return b"".join(result)
