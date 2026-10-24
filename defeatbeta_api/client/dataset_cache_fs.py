"""Demand-driven HTTP range cache for DefeatBeta's versioned Parquet dataset."""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from collections import OrderedDict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Callable, Optional
from urllib.parse import urlsplit

import fsspec
import httpx

from defeatbeta_api.client.shared_resources import (
    FILE_SIZES, FOOTERS, PARQUET_INDEXES, ParquetIndex, SharedHttpClient,
    dataset_file_identity, file_lock, value_size,
)
from defeatbeta_api.client.extent_index import ExtentIndex


_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
_LOG_URL_WITH_QUERY = re.compile(r"(https?://[^\s'\"?]+)\?[^\s'\"]*")
_CACHE_HTTPX_REQUEST = ContextVar("defeatbeta_cache_httpx_request", default=False)
_HTTPX_LOG_FILTER_LOCK = Lock()
_BLOCK_DIGEST_BYTES = hashlib.sha256().digest_size
_LEGACY_OBJECT_DIR = re.compile(r"[0-9a-f]{64}")
_LEGACY_OBJECT_FILE = re.compile(r"(?:size\.json|\d+-\d+\.block)")
_FLAT_CACHE_FILE = re.compile(
    r"(?P<version>[0-9a-f]{16})-[0-9a-f]{64}-[A-Za-z0-9_.-]+-"
    r"(?P<kind>size\.json|index\.json|\d+-\d+\.(?:block|footer))"
)
_MAX_IO_EXTENT_BYTES = 16 * 1024 * 1024
# fsspec requires a positive block size even with its pass-through cache.
_FSSPEC_NO_CACHE_BLOCK_SIZE_BYTES = 1
_MAX_MEMORY_EXTENTS = 64


def dataset_event_object_id(resolve_url):
    """Identify a pinned file in diagnostics without exposing its URL."""
    return hashlib.sha256(resolve_url.encode()).hexdigest()
_MAX_FOOTER_MEMORY_BYTES = 32 * 1024 * 1024
_INITIAL_FOOTER_TAIL_BYTES = 256 * 1024


class DatasetVersionChanged(RuntimeError):
    """A read or query outlived the dataset generation it started with."""


class _CacheHttpxLogFilter(logging.Filter):
    def filter(self, record):
        if _CACHE_HTTPX_REQUEST.get():
            message = record.getMessage()
            record.msg = _LOG_URL_WITH_QUERY.sub(r"\1?<redacted>", message)
            record.args = ()
        return True


_CACHE_HTTPX_LOG_FILTER = _CacheHttpxLogFilter()


def _install_cache_httpx_log_filter():
    logger = logging.getLogger("httpx")
    with _HTTPX_LOG_FILTER_LOCK:
        if _CACHE_HTTPX_LOG_FILTER not in logger.filters:
            logger.addFilter(_CACHE_HTTPX_LOG_FILTER)


@contextmanager
def parquet_metadata_file(footer_bytes):
    """Expose cached footer metadata to DuckDB without the original data pages."""
    if (len(footer_bytes) < 8 or footer_bytes[-4:] != b"PAR1"
            or int.from_bytes(footer_bytes[-8:-4], "little") != len(footer_bytes) - 8):
        raise ValueError("Invalid complete Parquet footer")
    with tempfile.TemporaryDirectory(prefix="defeatbeta-parquet-metadata-") as directory:
        path = Path(directory) / "metadata.parquet"
        path.write_bytes(b"PAR1" + footer_bytes)
        yield str(path)


class DatasetCacheFileSystem(fsspec.AbstractFileSystem):
    """Expose versioned remote files to DuckDB without a DuckDB binary extension.

    The cache stores demand-driven, variable-length byte ranges without
    materializing the entire remote object. A unique temporary file is
    renamed into place only after a complete response has been validated.
    """

    protocol = "defeatbeta"
    root_marker = ""
    cachable = False

    def __init__(
        self,
        directory: str,
        version: str,
        resolve: Callable[[str, bool], str],
        http_proxy: Optional[str] = None,
        max_disk_bytes: Optional[int] = None,
        max_memory_bytes: int = 64 * 1024 * 1024,
        workers: int = 3,
        timeout: float = 60,
        http_client=None,
        network_chunk_size: int = 0,
        footer_index: Optional[dict] = None,
        cache_enabled: bool = True,
        **kwargs,
    ):
        if "cache_layout" in kwargs:
            raise TypeError("cache_layout is no longer supported")
        super().__init__(**kwargs)
        if not version or workers < 1 or max_memory_bytes < 0:
            raise ValueError("Dataset cache version and limits must be positive")
        if max_disk_bytes is not None and max_disk_bytes <= 0:
            raise ValueError("Legacy disk cache limit must be positive")
        if network_chunk_size < 0:
            raise ValueError("Network chunk size must be nonnegative")
        _install_cache_httpx_log_filter()
        self.directory = Path(directory)
        self.cache_enabled = cache_enabled
        if cache_enabled:
            self.directory.mkdir(parents=True, exist_ok=True)
        self._version_file = self.directory / ".dataset-version.json"
        self._lock_file = self.directory / ".dataset-cache.lock"
        self.version = version
        self._version_tag = hashlib.sha256(version.encode()).hexdigest()[:16]
        self.resolve = resolve
        self.max_disk_bytes = max_disk_bytes  # Compatibility only; disk extents are retained.
        self.max_memory_bytes = max_memory_bytes
        self.network_chunk_size = network_chunk_size
        self._footer_index = footer_index if isinstance(footer_index, dict) else {}
        # Physical connections are pooled process-wide; this is a lightweight handle.
        self._client = http_client if http_client is not None else SharedHttpClient(
            proxy=http_proxy, trust_env=http_proxy is None, timeout=timeout)
        self._owns_client = http_client is None
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._network_executor = ThreadPoolExecutor(max_workers=workers)
        self._files = {}
        self._file_identities = {}
        self._file_version_tags = {}
        self._metadata_locks = {}
        self._pending = {}
        self._sizes = {}
        self._memory_blocks = OrderedDict()
        self._disk_index = None
        self._footer_memory = OrderedDict()
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
        self._read_events = deque(maxlen=4096)
        self._read_sequence = 0
        if cache_enabled:
            self._sync_version(version)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self._network_executor.shutdown(wait=True)
        self._disk_index = None
        if self._owns_client:
            self._client.close()

    def metrics(self):
        with self._guard:
            return dict(self._metrics)

    def range_event_sequence(self):
        with self._guard:
            return self._range_sequence

    def range_events(self, since=0):
        return self.range_event_snapshot(since)[0]

    def range_event_snapshot(self, since=0):
        with self._guard:
            events = [event for event in self._range_events
                      if event["sequence"] > since]
            complete = (self._range_sequence <= since or
                        bool(self._range_events) and
                        self._range_events[0]["sequence"] <= since + 1)
            return events, complete

    def range_events_complete(self, since=0):
        return self.range_event_snapshot(since)[1]

    def read_event_sequence(self):
        with self._guard:
            return self._read_sequence

    def read_events(self, since=0):
        return self.read_event_snapshot(since)[0]

    def read_event_snapshot(self, since=0):
        with self._guard:
            events = [event for event in self._read_events
                      if event["sequence"] > since]
            complete = (self._read_sequence <= since or
                        bool(self._read_events) and
                        self._read_events[0]["sequence"] <= since + 1)
            return events, complete

    def read_events_complete(self, since=0):
        return self.read_event_snapshot(since)[1]

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
            identity = dataset_file_identity(self.version, resolve_url, self._footer_index)
            key = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
            self._files[key] = resolve_url
            self._file_identities[key] = identity
            self._file_version_tags[key] = self._version_tag
        return f"{self.protocol}://{key}/{Path(parts.path).name}"

    def update_version(self, version: str, footer_index: Optional[dict] = None) -> None:
        """Move new reads to the current dataset and discard stale disk blocks."""
        if not version:
            raise ValueError("Dataset cache version must not be empty")
        with self._generation_lock:
            if self.cache_enabled:
                self._sync_version(version)
            else:
                self.version = version
                self._version_tag = hashlib.sha256(version.encode()).hexdigest()[:16]
            with self._guard:
                updated_index = footer_index if isinstance(footer_index, dict) else {}
                if updated_index != self._footer_index:
                    self._sizes.clear()
                    self._footer_memory.clear()
                self._footer_index = updated_index

    @contextmanager
    def _cache_lock(self):
        """Serialize atomic publication and dataset-version transitions."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock_file):
            yield

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
                        self._footer_memory.clear()
                        self._sizes.clear()
                retained = self._cleanup_stale_locked()
                ExtentIndex.retire_other_versions(self.directory, version)
                self._disk_index = ExtentIndex.shared(self.directory, version)
                self._disk_index.initialize(retained)

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

    def _cleanup_stale_locked(self):
        retained = []
        for entry in self.directory.iterdir():
            if entry.is_symlink():
                continue
            match = _FLAT_CACHE_FILE.fullmatch(entry.name)
            if match is not None and entry.is_file():
                if (match.group("version") != self._version_tag
                        or match.group("kind") in ("size.json", "index.json")):
                    try:
                        entry.unlink()
                    except OSError:
                        pass
                else:
                    retained.append(entry.name)
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
        return retained

    def _current_key(self, key):
        with self._guard:
            return self._current_key_locked(key)

    def _current_key_locked(self, key):
        return self._file_identities[key] == dataset_file_identity(
            self.version, self._files[key], self._footer_index)

    def _require_current_key(self, key):
        if not self._current_key(key):
            raise DatasetVersionChanged("Dataset version changed during the read")

    def _key_and_url(self, path):
        stripped = self._strip_protocol(str(path)).lstrip("/")
        key = stripped.split("/", 1)[0]
        with self._guard:
            url = self._files.get(key)
        if url is None:
            raise FileNotFoundError("Unknown DefeatBeta dataset cache path")
        self._require_current_key(key)
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
            for attempt in range(2):
                try:
                    token = _CACHE_HTTPX_REQUEST.set(True)
                    try:
                        response = self._client.get(
                            signed_url,
                            headers={"Range": f"bytes={start}-{end}",
                                     "Accept-Encoding": "identity"},
                        )
                    finally:
                        _CACHE_HTTPX_REQUEST.reset(token)
                except httpx.TransportError:
                    if attempt == 0:
                        continue
                    raise
                break
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
                    "file": Path(urlsplit(url).path).name,
                    "object_id": dataset_event_object_id(url),
                    "start": start,
                    "end": end,
                    "bytes": len(response.content),
                    "seconds": time.perf_counter() - started,
                    "http_version": response.http_version,
                })
            return response.content, total
        raise RuntimeError("Signed dataset URL expired after refresh")

    def _spec_size(self, url):
        relative_path = urlsplit(url).path.partition("/data/")[2]
        with self._guard:
            hint = self._footer_index.get(relative_path)
            hinted_size = hint.get("file_size") if isinstance(hint, dict) else None
        return hinted_size if type(hinted_size) is int and hinted_size > 0 else None

    def _get_size(self, key, url):
        hinted_size = self._spec_size(url)
        if hinted_size is not None:
            with self._guard:
                self._sizes[key] = hinted_size
            return hinted_size
        with self._guard:
            cached_size = self._sizes.get(key)
        if cached_size is not None:
            return cached_size
        with self._guard:
            lock = self._metadata_locks.setdefault(key, Lock())
        with lock:
            with self._guard:
                cached_size = self._sizes.get(key)
            if cached_size is not None:
                return cached_size
            def build():
                resolved = self.resolve(url, False)
                size = resolved[1] if isinstance(resolved, tuple) else None
                if not isinstance(size, int) or size <= 0:
                    _, size = self._request_range(url, 0, 0)
                return size

            size = FILE_SIZES.get_or_build((str(self.directory.resolve()), key), build)
            with self._guard:
                if self._current_key_locked(key):
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

    def _publish_extent(self, target, content):
        self._atomic_write(target, hashlib.sha256(content).digest() + content)
        self._disk_index.add(target.name)

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
            self, path, mode="rb", block_size=_FSSPEC_NO_CACHE_BLOCK_SIZE_BYTES,
            cache_type="none", size=self.info(path)["size"],
        )

    def _block_path(self, key, start, length):
        return self.directory / f"{self._object_name(key)}-{start}-{length}.block"

    def _footer_path(self, key, start, length):
        return self.directory / f"{self._object_name(key)}-{start}-{length}.footer"

    @staticmethod
    def _footer_size(content, start, total):
        if len(content) < 8 or content[-4:] != b"PAR1":
            raise ValueError("Remote Parquet footer has no valid magic bytes")
        footer_size = int.from_bytes(content[-8:-4], "little")
        if (footer_size <= 0 or footer_size > _MAX_IO_EXTENT_BYTES
                or total - footer_size - 8 < start):
            raise ValueError("Remote Parquet footer has an invalid length")
        return footer_size

    def _remember_footer(self, key, start, content, footer_size):
        with self._guard:
            self._remember_footer_locked(key, start, content, footer_size)

    def _remember_footer_locked(self, key, start, content, footer_size):
        self._footer_memory.pop(key, None)
        self._footer_memory[key] = (start, content, footer_size)
        while (sum(len(item[1]) for item in self._footer_memory.values())
               > _MAX_FOOTER_MEMORY_BYTES):
            self._footer_memory.popitem(last=False)

    def _load_footer(self, key, total):
        with self._guard:
            if not self._current_key_locked(key):
                return None
            footer_index = self._footer_index
            url = self._files[key]
            hint = footer_index.get(urlsplit(url).path.partition("/data/")[2])
            remembered = self._footer_memory.get(key)

        def still_current():
            return self._current_key_locked(key)

        def matches_hint(content, footer_size):
            if not isinstance(hint, dict) or hint.get("file_size") != total:
                return True
            expected = hint.get("footer_sha256")
            if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                return True
            return (hint.get("footer_size") == footer_size
                    and hashlib.sha256(content[-footer_size - 8:-8]).hexdigest() == expected)

        if remembered is not None:
            start, content, footer_size = remembered
            if start + len(content) == total and matches_hint(content, footer_size):
                with self._guard:
                    if not still_current():
                        return None
                    # Eviction does not invalidate immutable bytes already
                    # borrowed by this reader. Do not resurrect the entry.
                    if self._footer_memory.get(key) is remembered:
                        self._footer_memory.move_to_end(key)
                    return remembered
        for start, end, kind, name in self._disk_index.overlapping(self._object_name(key), 0, total):
            if kind != "footer":
                continue
            path = self.directory / name
            length = end - start
            if start + length != total or length > _MAX_IO_EXTENT_BYTES:
                continue
            content = self._read_block(path, length)
            if content is None:
                continue
            try:
                footer_size = self._footer_size(content, start, total)
            except ValueError:
                continue
            if not matches_hint(content, footer_size):
                continue
            with self._guard:
                if not still_current():
                    return None
                self._remember_footer_locked(key, start, content, footer_size)
                return start, content, footer_size
        return None

    def prepare_footer(self, path):
        """Persist a validated Parquet tail that covers the complete footer."""
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        if total < 12:
            raise ValueError("Remote Parquet footer is too short")
        with self._guard:
            lock = self._metadata_locks.setdefault(key, Lock())
        with lock:
            def build():
                # The local process lock coalesces downloads; disk publication
                # remains atomic and guarded against a version change.
                # Keep one lock inode per URL across data versions. Never unlink
                # lock files that other processes may already have opened.
                lock_id = dataset_event_object_id(url)
                with file_lock(self.directory / f".footer-{lock_id}.lock"):
                    self._prepare_footer_locked(key, url, total)
                footer = self._load_footer(key, total)
                if footer is None or not self._current_key(key):
                    raise ValueError("Dataset version changed during footer preparation")
                target = self._footer_path(key, footer[0], len(footer[1]))
                stat = target.stat()
                return footer, target, (stat.st_ino, stat.st_mtime_ns, stat.st_size)

            def valid(item):
                try:
                    stat = item[1].stat()
                    return (stat.st_ino, stat.st_mtime_ns, stat.st_size) == item[2]
                except OSError:
                    return False

            shared_key = (key, total)
            footer, _, _ = FOOTERS.get_or_build(
                shared_key, build, valid=valid, weight=lambda item: len(item[0][1]))
            if not self._current_key(key):
                raise ValueError("Dataset version changed during footer preparation")
            target = self._footer_path(key, footer[0], len(footer[1]))
            if not target.exists():
                with self._generation_lock, self._cache_lock():
                    if self._current_key(key) and self._stored_version() == self.version:
                        if not target.exists():
                            self._publish_extent(target, footer[1])
            self._remember_footer(key, *footer)
            return footer[2]

    def cached_footer_bytes(self, path):
        """Return the exact footer and trailer after footer preparation."""
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        footer = self._load_footer(key, total)
        if footer is None:
            raise ValueError("Parquet footer has not been prepared")
        return footer[1][-(footer[2] + 8):]

    def shared_parquet_index(self, path, footer_bytes, build):
        """Share immutable parsed metadata, including format and footer identity."""
        import duckdb

        key, _ = self._key_and_url(path)
        identity = (key, hashlib.sha256(footer_bytes).digest(),
                    duckdb.__version__, 1)
        return PARQUET_INDEXES.get_or_build(
            identity, lambda: ParquetIndex(tuple(tuple(row) for row in build())),
            weight=lambda index: value_size(index.rows))

    def _prepare_footer_locked(self, key, url, total):
        existing = self._load_footer(key, total)
        if existing is not None:
            return existing[2]
        relative_path = urlsplit(url).path.partition("/data/")[2]
        with self._guard:
            hint = self._footer_index.get(relative_path)
        hinted_size = hint.get("footer_size") if isinstance(hint, dict) else None
        hinted_hash = hint.get("footer_sha256") if isinstance(hint, dict) else None
        valid_hint = (
            isinstance(hint, dict)
            and type(hint.get("file_size")) is int
            and hint["file_size"] == total
            and type(hinted_size) is int
            and 0 < hinted_size <= min(_MAX_IO_EXTENT_BYTES - 8, total - 12)
            and isinstance(hinted_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", hinted_hash) is not None
        )
        tail_size = hinted_size + 8 if valid_hint else _INITIAL_FOOTER_TAIL_BYTES
        start = max(0, total - tail_size)
        # Preserve the existing footer-lock handoff without rescanning data files.
        # A waiter can check the one tail path determined by the footer policy.
        target = self._footer_path(key, start, total - start)
        if not target.is_symlink() and target.is_file():
            self._disk_index.add(target.name)
            existing = self._load_footer(key, total)
            if existing is not None:
                return existing[2]
        tail, _ = self._request_range(url, start, total - 1, total)
        if len(tail) < 8 or tail[-4:] != b"PAR1":
            raise ValueError("Remote Parquet footer has no valid magic bytes")
        footer_size = int.from_bytes(tail[-8:-4], "little")
        if footer_size <= 0 or footer_size > _MAX_IO_EXTENT_BYTES - 8:
            raise ValueError("Remote Parquet footer has an invalid length")
        if valid_hint and (
            footer_size != hinted_size
            or hashlib.sha256(tail[:-8]).hexdigest() != hinted_hash
        ):
            raise ValueError("Remote Parquet footer does not match spec.json")
        footer_start = total - footer_size - 8
        if footer_start < 4:
            raise ValueError("Remote Parquet footer overlaps the file header")
        if footer_start < start:
            prefix, _ = self._request_range(url, footer_start, start - 1, total)
            tail = prefix + tail
            start = footer_start
        self._footer_size(tail, start, total)
        target = self._footer_path(key, start, len(tail))
        with self._generation_lock:
            with self._cache_lock():
                if self._current_key(key) and self._stored_version() == self.version:
                    self._publish_extent(target, tail)
                    self._remember_footer(key, start, tail, footer_size)
        return footer_size

    def _read_block(self, path, length):
        try:
            if path.is_symlink():
                return None
            stored = path.read_bytes()
            digest, content = stored[:_BLOCK_DIGEST_BYTES], stored[_BLOCK_DIGEST_BYTES:]
            if (len(content) == length and len(digest) == _BLOCK_DIGEST_BYTES
                    and hashlib.sha256(content).digest() == digest):
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
        if self.max_memory_bytes == 0:
            return
        with self._guard:
            self._memory_blocks.pop(cache_key, None)
            self._memory_blocks[cache_key] = content
            while (len(self._memory_blocks) > _MAX_MEMORY_EXTENTS
                   or sum(map(len, self._memory_blocks.values()))
                   > self.max_memory_bytes):
                self._memory_blocks.popitem(last=False)

    def _fetch_block(self, key, url, start, length, total):
        self._require_current_key(key)
        cache_key = (key, start, length)
        in_memory = self._memory_get(cache_key)
        if in_memory is not None:
            return in_memory
        target = self._block_path(key, start, length)
        existing = self._read_block(target, length)
        if existing is not None:
            self._memory_put(cache_key, existing)
            return existing
        if self.network_chunk_size and length > self.network_chunk_size:
            futures = [
                self._network_executor.submit(
                    self._request_range, url, offset,
                    min(offset + self.network_chunk_size, start + length) - 1,
                    total,
                )
                for offset in range(start, start + length, self.network_chunk_size)
            ]
            content = b"".join(future.result()[0] for future in futures)
        else:
            content, _ = self._request_range(url, start, start + length - 1, total)
        with self._generation_lock:
            self._require_current_key(key)
            with self._cache_lock():
                if self._stored_version() != self.version:
                    return content
                try:
                    # Another owner may have published an overlapping download.
                    extents = self._cached_extents(key, start, start + length)
                    for left, right in self._uncovered_intervals(start, start + length, extents):
                        part = content[left - start:right - start]
                        self._publish_extent(self._block_path(key, left, right - left), part)
                        self._memory_put((key, left, right - left), part)
                except OSError:
                    # Cache storage is optional once the remote bytes are validated.
                    return content
        return content

    def _forget_pending(self, pending_key, future):
        with self._guard:
            if self._pending.get(pending_key) is future:
                self._pending.pop(pending_key, None)

    def prefetch_ranges(self, path, ranges):
        """Start independent, unaligned byte ranges without waiting for them."""
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        for start, end in ranges:
            if not (isinstance(start, int) and isinstance(end, int)
                    and 0 <= start < end <= total):
                raise ValueError("Prefetch range is outside the remote file")
            self._schedule_io_extents(key, url, start, end, total)

    def await_pending(self):
        """Wait for already scheduled reads without changing query behavior."""
        with self._guard:
            futures = list(self._pending.values())
        errors = 0
        for future in futures:
            try:
                future.result()
            except Exception:
                errors += 1
        return {"futures": len(futures), "errors": errors}

    def cat_file(self, path, start=None, end=None, **kwargs):
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        start = 0 if start is None else max(0, start)
        end = total if end is None else min(end, total)
        if end <= start:
            return b""
        with self._guard:
            self._read_sequence += 1
            self._read_events.append({
                "sequence": self._read_sequence,
                "file": Path(urlsplit(url).path).name,
                "object_id": dataset_event_object_id(url),
                "start": start,
                "end": end,
                "bytes": end - start,
            })
        if not self.cache_enabled:
            content = self._request_range(url, start, end - 1, total)[0]
        else:
            content = self._cat_io(key, url, start, end, total)
        self._require_current_key(key)
        return content

    def _cached_extents(self, key, start, end):
        """Read validated on-disk intervals that overlap a requested range."""
        extents = []
        with self._guard:
            footer = self._footer_memory.get(key)
            if footer is not None:
                offset, content, _ = footer
                if offset < end and offset + len(content) > start:
                    self._footer_memory.move_to_end(key)
                    self._metrics["cache_hits"] += 1
                    extents.append((offset, offset + len(content), content))
        for offset, extent_end, kind, name in self._disk_index.overlapping(self._object_name(key), start, end):
            if kind == "footer" and footer is not None:
                continue
            length = extent_end - offset
            path = self.directory / name
            cache_key = (key, offset, length)
            content = self._memory_get(cache_key)
            if content is None:
                content = self._read_block(path, length)
                if content is not None:
                    self._memory_put(cache_key, content)
            if content is not None:
                extents.append((offset, offset + length, content))
        return extents

    @staticmethod
    def _uncovered_intervals(start, end, extents):
        cursor = start
        for extent_start, extent_end, _ in sorted(extents, key=lambda item: item[0]):
            if extent_start > cursor:
                yield cursor, min(extent_start, end)
            cursor = max(cursor, extent_end)
            if cursor >= end:
                return
        if cursor < end:
            yield cursor, end

    def _pending_extents_locked(self, key, start, end):
        return [(offset, offset + length, future)
                for (pending_key, offset, length), future in self._pending.items()
                if pending_key == key and offset < end and offset + length > start]

    def _schedule_io_extents(self, key, url, start, end, total):
        # A download leaves _pending only after publishing its extent. Snapshot
        # in-flight ranges before reading the disk index, so a range finishing
        # between the two checks is seen by at least one of them.
        with self._guard:
            in_flight = self._pending_extents_locked(key, start, end)
        extents = self._cached_extents(key, start, end) + in_flight
        max_extent = _MAX_IO_EXTENT_BYTES
        scheduled = []
        with self._guard:
            extents.extend(self._pending_extents_locked(key, start, end))
            missing = list(self._uncovered_intervals(start, end, extents))
            for gap_start, gap_end in missing:
                for offset in range(gap_start, gap_end, max_extent):
                    length = min(max_extent, gap_end - offset)
                    pending_key = (key, offset, length)
                    future = self._executor.submit(
                        self._fetch_block, key, url, offset, length, total
                    )
                    self._pending[pending_key] = future
                    self._metrics["cache_misses"] += 1
                    scheduled.append((pending_key, future))
                    extents.append((offset, offset + length, future))
        for pending_key, future in scheduled:
            future.add_done_callback(
                lambda completed, item=pending_key: self._forget_pending(item, completed)
            )
        return extents

    def _cat_io(self, key, url, start, end, total):
        extents = self._schedule_io_extents(key, url, start, end, total)
        result = bytearray(end - start)
        for offset, extent_end, content in extents:
            if isinstance(content, Future):
                content = content.result()
            overlap_start = max(start, offset)
            overlap_end = min(end, extent_end)
            if overlap_start < overlap_end:
                result[overlap_start - start:overlap_end - start] = (
                    content[overlap_start - offset:overlap_end - offset]
                )
        return bytes(result)


class DatasetNetworkFileSystem(DatasetCacheFileSystem):
    """Use the same shared range transport with a distinct uncached protocol."""

    protocol = "defeatbeta-network"
