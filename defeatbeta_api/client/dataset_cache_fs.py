"""Demand-driven HTTP range cache for DefeatBeta's versioned Parquet dataset."""

import hashlib
import json
import os
import re
import tempfile
import time
from collections import OrderedDict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Callable, Optional
from urllib.parse import urlsplit

import fsspec
import httpx


_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
_BLOCK_DIGEST_BYTES = hashlib.sha256().digest_size
_LEGACY_OBJECT_DIR = re.compile(r"[0-9a-f]{64}")
_LEGACY_OBJECT_FILE = re.compile(r"(?:size\.json|\d+-\d+\.block)")
_FLAT_CACHE_FILE = re.compile(
    r"(?P<version>[0-9a-f]{16})-[0-9a-f]{64}-[A-Za-z0-9_.-]+-"
    r"(?:size\.json|\d+-\d+\.block)"
)


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
        self._version_file = self.directory / ".dataset-version.json"
        self._lock_file = self.directory / ".dataset-cache.lock"
        self.version = version
        self._version_tag = hashlib.sha256(version.encode()).hexdigest()[:16]
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
        self._file_version_tags = {}
        self._metadata_locks = {}
        self._pending = {}
        self._sizes = {}
        self._memory_blocks = OrderedDict()
        self._guard = Lock()
        self._generation_lock = RLock()
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "downloaded_bytes": 0,
            "range_requests": 0,
            "range_seconds": 0.0,
        }
        self._range_events = deque(maxlen=1024)
        self._range_sequence = 0
        self._sync_version(version)

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
        with self._guard:
            key = hashlib.sha256(
                f"{self.version}\n{resolve_url}".encode()
            ).hexdigest()
            self._files[key] = resolve_url
            self._file_version_tags[key] = self._version_tag
        return f"{self.protocol}://{key}/{Path(parts.path).name}"

    def update_version(self, version: str) -> None:
        """Move new reads to the current dataset and discard stale disk blocks."""
        if not version:
            raise ValueError("Dataset cache version must not be empty")
        self._sync_version(version)

    @contextmanager
    def _cache_lock(self):
        """Serialize cache publication and eviction across local processes."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._lock_file.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt

                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _stored_version(self):
        try:
            version = json.loads(self._version_file.read_text(encoding="utf-8"))["version"]
            return version if isinstance(version, str) and version else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _sync_version(self, version):
        with self._generation_lock:
            with self._cache_lock():
                stored = self._stored_version()
                candidate_time = self._version_time(version)
                for active in (stored, self.version):
                    active_time = self._version_time(active)
                    if (candidate_time is not None and active_time is not None
                            and candidate_time < active_time):
                        raise ValueError("Remote dataset version is older than the active cache")
                if stored != version:
                    self._atomic_write(
                        self._version_file, json.dumps({"version": version}).encode()
                    )
                with self._guard:
                    if version != self.version:
                        self.version = version
                        self._version_tag = hashlib.sha256(version.encode()).hexdigest()[:16]
                        self._memory_blocks.clear()
                        self._sizes.clear()
                self._cleanup_stale_locked()

    @staticmethod
    def _version_time(version):
        if not isinstance(version, str):
            return None
        try:
            parsed = datetime.fromisoformat(version.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else None
        except ValueError:
            return None

    def cleanup_stale(self) -> None:
        """Remove only stale cache-owned files, retrying occupied files later."""
        with self._generation_lock:
            with self._cache_lock():
                if self._stored_version() == self.version:
                    self._cleanup_stale_locked()

    def _cleanup_stale_locked(self) -> None:
        for entry in self.directory.iterdir():
            if entry.is_symlink():
                continue
            match = _FLAT_CACHE_FILE.fullmatch(entry.name)
            if match is not None and entry.is_file():
                if match.group("version") != self._version_tag:
                    try:
                        entry.unlink()
                    except OSError:
                        pass
                continue
            if not _LEGACY_OBJECT_DIR.fullmatch(entry.name) or not entry.is_dir():
                continue
            try:
                children = list(entry.iterdir())
            except OSError:
                continue
            if not all(
                not child.is_symlink() and child.is_file()
                and _LEGACY_OBJECT_FILE.fullmatch(child.name)
                for child in children
            ):
                continue
            for child in children:
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                entry.rmdir()
            except OSError:
                pass

    def _current_key(self, key):
        with self._guard:
            return self._file_version_tags[key] == self._version_tag

    def _key_and_url(self, path):
        stripped = self._strip_protocol(str(path)).lstrip("/")
        key = stripped.split("/", 1)[0]
        with self._guard:
            url = self._files.get(key)
        if url is None:
            raise FileNotFoundError("Unknown DefeatBeta dataset cache path")
        return key, url

    def _object_name(self, key):
        with self._guard:
            url = self._files[key]
            version_tag = self._file_version_tags[key]
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(urlsplit(url).path).name)[:48]
        return f"{version_tag}-{key}-{name}"

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
        metadata = self.directory / f"{self._object_name(key)}-size.json"
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
            with self._generation_lock:
                with self._cache_lock():
                    if self._current_key(key) and self._stored_version() == self.version:
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
        return self.directory / f"{self._object_name(key)}-{start}-{length}.block"

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
        with self._generation_lock:
            with self._cache_lock():
                if not self._current_key(key) or self._stored_version() != self.version:
                    return content
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
