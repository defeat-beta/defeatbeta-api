"""Demand-driven HTTP range cache for DefeatBeta's versioned Parquet dataset."""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from collections import OrderedDict, deque
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from typing import Callable, Optional
from urllib.parse import urlsplit

import fsspec
import httpx


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
_POOL_LOG_INTERVAL_SECONDS = 60
_MAX_ORIGIN_GROUPS = 32
_MAX_IO_EXTENT_BYTES = 16 * 1024 * 1024
# fsspec requires a positive block size even with its pass-through cache.
_FSSPEC_NO_CACHE_BLOCK_SIZE_BYTES = 1
_CONNECTION_WARMUP_SPACING_BYTES = 1024 * 1024
_MAX_MEMORY_EXTENTS = 64


def dataset_event_object_id(resolve_url):
    """Identify a pinned file in diagnostics without exposing its URL."""
    return hashlib.sha256(resolve_url.encode()).hexdigest()
_MAX_FOOTER_MEMORY_BYTES = 32 * 1024 * 1024
_INITIAL_FOOTER_TAIL_BYTES = 256 * 1024
_EXTENT_SUFFIX = re.compile(
    r"(?P<start>\d+)-(?P<length>\d+)\.(?P<kind>block|footer)"
)


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
        max_disk_bytes: int = 5 * 1024 * 1024 * 1024,
        max_memory_bytes: int = 64 * 1024 * 1024,
        workers: int = 3,
        timeout: float = 60,
        http_client=None,
        network_connections: int = 1,
        network_chunk_size: int = 0,
        footer_index: Optional[dict] = None,
        logger: Optional[logging.Logger] = None,
        **kwargs,
    ):
        if "cache_layout" in kwargs:
            raise TypeError("cache_layout is no longer supported")
        super().__init__(**kwargs)
        if (not version or min(max_disk_bytes, workers) <= 0
                or max_memory_bytes < 0):
            raise ValueError("Dataset cache version and limits must be positive")
        if max_disk_bytes < _BLOCK_DIGEST_BYTES + 1:
            raise ValueError("Disk cache limit must hold one data byte and its digest")
        if network_connections < 1 or network_chunk_size < 0:
            raise ValueError("Network connection and chunk limits must be nonnegative")
        if http_client is not None and network_connections != 1:
            raise ValueError("Injected HTTP client requires one network connection")
        _install_cache_httpx_log_filter()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._version_file = self.directory / ".dataset-version.json"
        self._lock_file = self.directory / ".dataset-cache.lock"
        self.version = version
        self._version_tag = hashlib.sha256(version.encode()).hexdigest()[:16]
        self.resolve = resolve
        self.max_disk_bytes = max_disk_bytes
        self.max_memory_bytes = max_memory_bytes
        self.network_chunk_size = network_chunk_size
        self._footer_index = footer_index if isinstance(footer_index, dict) else {}
        self._network_connections = network_connections
        self._http_proxy = http_proxy
        self._timeout = timeout
        self._workers = workers
        self._clients = [http_client] if http_client is not None else self._new_clients()
        self._client = self._clients[0]
        self._owns_client = http_client is None
        self._initial_clients_unassigned = True
        self._origin_pools = OrderedDict()
        self._executor = ThreadPoolExecutor(max_workers=workers)
        network_workers = network_connections if network_connections > 1 else workers
        self._network_executor = ThreadPoolExecutor(max_workers=network_workers)
        self._client_lock = Lock()
        self._files = {}
        self._file_version_tags = {}
        self._metadata_locks = {}
        self._pending = {}
        self._sizes = {}
        self._memory_blocks = OrderedDict()
        self._memory_access_ns = {}
        self._last_memory_access_ns = 0
        self._footer_memory = OrderedDict()
        self._guard = Lock()
        self._client_observations = [
            {"last_result": "unobserved", "last_observed_at": None,
             "successful_ranges": 0, "transport_errors": 0}
            for _ in self._clients
        ]
        self._pool_log_stop = Event()
        self._pool_logger = logger or logging.getLogger(self.__class__.__name__)
        self._generation_lock = RLock()
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "downloaded_bytes": 0,
            "range_requests": 0,
            "range_seconds": 0.0,
        }
        self._warmup_metrics = {
            "downloaded_bytes": 0,
            "range_requests": 0,
            "range_seconds": 0.0,
        }
        self._range_events = deque(maxlen=1024)
        self._range_sequence = 0
        self._read_events = deque(maxlen=4096)
        self._read_sequence = 0
        self._sync_version(version)
        self._pool_log_thread = Thread(
            target=self._log_connection_pool, name="DefeatBetaCachePool", daemon=True
        )
        self._pool_log_thread.start()

    def _new_clients(self):
        return [
            httpx.Client(
                http2=True,
                proxy=self._http_proxy or None,
                trust_env=self._http_proxy is None,
                timeout=self._timeout,
                limits=httpx.Limits(
                    max_connections=1 if self._network_connections > 1 else self._workers,
                    max_keepalive_connections=1 if self._network_connections > 1 else self._workers,
                    keepalive_expiry=120,
                ),
            )
            for _ in range(self._network_connections)
        ]

    def close(self) -> None:
        self._pool_log_stop.set()
        self._pool_log_thread.join()
        self._executor.shutdown(wait=True)
        self._network_executor.shutdown(wait=True)
        if self._owns_client:
            with self._client_lock:
                groups = [pool["clients"] for pool in self._origin_pools.values()]
                if self._initial_clients_unassigned:
                    groups.append(self._clients)
            for client in {id(client): client for group in groups for client in group}.values():
                client.close()

    def metrics(self):
        with self._guard:
            return dict(self._metrics)

    def warmup_metrics(self):
        with self._guard:
            return dict(self._warmup_metrics)

    def connection_snapshot(self):
        """Return last observed request outcomes, not socket liveness."""
        now = time.monotonic()
        with self._client_lock:
            tracked_origins = len(self._origin_pools)
            active_ranges = sum(pool["active"] for pool in self._origin_pools.values())
            groups = [
                (origin, list(pool["observations"]))
                for origin, pool in self._origin_pools.items()
            ]
            if self._initial_clients_unassigned:
                groups.append((None, list(self._client_observations)))
        with self._guard:
            clients = [
                {
                    "index": index,
                    "origin_host": None if origin is None else origin[1],
                    "origin_port": None if origin is None else origin[2],
                    "last_result": item["last_result"],
                    "last_observed_seconds_ago": (
                        None if item["last_observed_at"] is None
                        else max(0.0, now - item["last_observed_at"])
                    ),
                    "successful_ranges": item["successful_ranges"],
                    "transport_errors": item["transport_errors"],
                }
                for origin, observations in groups
                for index, item in enumerate(observations)
            ]
        return {
            "observation_only": True,
            "tracked_origins": tracked_origins,
            "active_ranges": active_ranges,
            "clients": clients,
        }

    def _observe_client(self, item, result):
        with self._guard:
            item["last_result"] = result
            item["last_observed_at"] = time.monotonic()
            if result == "range_ok":
                item["successful_ranges"] += 1
            elif result == "transport_error":
                item["transport_errors"] += 1

    @staticmethod
    def _origin(signed_url):
        parts = urlsplit(signed_url)
        return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)

    def _trim_origin_pools_locked(self, protected=None):
        closing = []
        while len(self._origin_pools) > _MAX_ORIGIN_GROUPS:
            victim = next(
                (origin for origin, pool in self._origin_pools.items()
                 if origin != protected and pool["active"] == 0), None
            )
            if victim is None:
                break
            pool = self._origin_pools.pop(victim)
            if self._owns_client:
                closing.extend(pool["clients"])
        return closing

    def _borrow_client(self, signed_url, lane=None):
        origin = self._origin(signed_url)
        with self._client_lock:
            pool = self._origin_pools.get(origin)
            if pool is None:
                if self._initial_clients_unassigned:
                    clients = self._clients
                    observations = self._client_observations
                    self._initial_clients_unassigned = False
                elif self._owns_client:
                    clients = self._new_clients()
                    observations = [
                        {"last_result": "unobserved", "last_observed_at": None,
                         "successful_ranges": 0, "transport_errors": 0}
                        for _ in clients
                    ]
                else:
                    clients = self._clients
                    observations = self._client_observations
                pool = {"clients": clients, "observations": observations,
                        "active": 0, "next": 0}
                self._origin_pools[origin] = pool
            index = pool["next"] % len(pool["clients"]) if lane is None else lane
            if lane is None:
                pool["next"] += 1
            pool["active"] += 1
            self._origin_pools.move_to_end(origin)
            closing = self._trim_origin_pools_locked(protected=origin)
            client = pool["clients"][index]
            observation = pool["observations"][index]
        for stale in closing:
            stale.close()
        return client, observation, origin

    def _release_client(self, origin):
        with self._client_lock:
            pool = self._origin_pools[origin]
            pool["active"] -= 1
            self._origin_pools.move_to_end(origin)
            closing = self._trim_origin_pools_locked()
        for stale in closing:
            stale.close()

    def _log_connection_pool(self):
        while not self._pool_log_stop.wait(_POOL_LOG_INTERVAL_SECONDS):
            if self._pool_logger.isEnabledFor(logging.DEBUG):
                self._pool_logger.debug(
                    "Connection pool request observations (no liveness probe): %s",
                    self.connection_snapshot(),
                )

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
            key = hashlib.sha256(
                f"{self.version}\n{resolve_url}".encode()
            ).hexdigest()
            self._files[key] = resolve_url
            self._file_version_tags[key] = self._version_tag
        return f"{self.protocol}://{key}/{Path(parts.path).name}"

    def update_version(self, version: str, footer_index: Optional[dict] = None) -> None:
        """Move new reads to the current dataset and discard stale disk blocks."""
        if not version:
            raise ValueError("Dataset cache version must not be empty")
        with self._generation_lock:
            self._sync_version(version)
            with self._guard:
                updated_index = footer_index if isinstance(footer_index, dict) else {}
                if updated_index != self._footer_index:
                    self._sizes.clear()
                self._footer_index = updated_index

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
                        self._memory_access_ns.clear()
                        self._last_memory_access_ns = 0
                        self._footer_memory.clear()
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
                if (match.group("version") != self._version_tag
                        or match.group("kind") in ("size.json", "index.json")):
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

    def _request_range(self, url, start, end, expected_total=None, lane=None,
                       *, warmup=False):
        started = time.perf_counter()
        for refresh in (False, True):
            resolved = self.resolve(url, refresh)
            signed_url = resolved[0] if isinstance(resolved, tuple) else resolved
            client, observation, origin = self._borrow_client(signed_url, lane)
            try:
                for attempt in range(2):
                    try:
                        token = _CACHE_HTTPX_REQUEST.set(True)
                        try:
                            response = client.get(
                                signed_url,
                                headers={"Range": f"bytes={start}-{end}",
                                         "Accept-Encoding": "identity"},
                            )
                        finally:
                            _CACHE_HTTPX_REQUEST.reset(token)
                    except httpx.TransportError:
                        self._observe_client(observation, "transport_error")
                        if attempt == 0:
                            continue
                        raise
                    break
                if response.status_code in (401, 403) and not refresh:
                    self._observe_client(observation, f"http_{response.status_code}")
                    continue
                try:
                    total = self._check_response(response, start, end, expected_total)
                except ValueError:
                    self._observe_client(observation, "invalid_range")
                    raise
                self._observe_client(observation, "range_ok")
                with self._guard:
                    metrics = self._warmup_metrics if warmup else self._metrics
                    metrics["range_requests"] += 1
                    metrics["downloaded_bytes"] += len(response.content)
                    metrics["range_seconds"] += time.perf_counter() - started
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
            finally:
                self._release_client(origin)
        raise RuntimeError("Signed dataset URL expired after refresh")

    def prepare_connections(self, resolve_url, warmup_bytes):
        """Warm independent transport connections without publishing cache blocks."""
        if warmup_bytes < 1 or warmup_bytes > _CONNECTION_WARMUP_SPACING_BYTES:
            raise ValueError("Warmup size must fit inside one warmup interval")
        resolved = self.resolve(resolve_url, False)
        size = resolved[1] if isinstance(resolved, tuple) else None
        if not isinstance(size, int) or size <= 0:
            size = self._spec_size(resolve_url)
        if size is None:
            _, size = self._request_range(resolve_url, 0, 0, warmup=True)
        neutral_start = 24 * _CONNECTION_WARMUP_SPACING_BYTES
        if (neutral_start
                + self._network_connections * _CONNECTION_WARMUP_SPACING_BYTES > size):
            raise ValueError("Remote file is too small for disjoint connection warmup")
        futures = [
            self._network_executor.submit(
                self._request_range, resolve_url,
                neutral_start + index * _CONNECTION_WARMUP_SPACING_BYTES,
                neutral_start + index * _CONNECTION_WARMUP_SPACING_BYTES
                + warmup_bytes - 1,
                size, index, warmup=True,
            )
            for index in range(self._network_connections)
        ]
        wait(futures)
        for future in futures:
            future.result()

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
            resolved = self.resolve(url, False)
            size = resolved[1] if isinstance(resolved, tuple) else None
            if not isinstance(size, int) or size <= 0:
                _, size = self._request_range(url, 0, 0)
            with self._guard:
                if self._file_version_tags[key] == self._version_tag:
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
            self._footer_memory.pop(key, None)
            self._footer_memory[key] = (start, content, footer_size)
            while (sum(len(item[1]) for item in self._footer_memory.values())
                   > _MAX_FOOTER_MEMORY_BYTES):
                self._footer_memory.popitem(last=False)

    def _load_footer(self, key, total):
        with self._guard:
            remembered = self._footer_memory.get(key)
            if remembered is not None:
                start, content, footer_size = remembered
                if start + len(content) == total:
                    self._footer_memory.move_to_end(key)
                    return remembered
        prefix = f"{self._object_name(key)}-"
        for path in self.directory.iterdir():
            if path.is_symlink() or not path.is_file() or not path.name.startswith(prefix):
                continue
            match = _EXTENT_SUFFIX.fullmatch(path.name[len(prefix):])
            if match is None or match.group("kind") != "footer":
                continue
            start = int(match.group("start"))
            length = int(match.group("length"))
            if start + length != total or length > _MAX_IO_EXTENT_BYTES:
                continue
            content = self._read_block(path, length)
            if content is None:
                continue
            try:
                footer_size = self._footer_size(content, start, total)
            except ValueError:
                continue
            self._remember_footer(key, start, content, footer_size)
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
            return self._prepare_footer_locked(key, url, total)

    def cached_footer_bytes(self, path):
        """Return the exact footer and trailer after footer preparation."""
        key, url = self._key_and_url(path)
        total = self._get_size(key, url)
        footer = self._load_footer(key, total)
        if footer is None:
            raise ValueError("Parquet footer has not been prepared")
        return footer[1][-(footer[2] + 8):]

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
                    self._atomic_write(target, hashlib.sha256(tail).digest() + tail)
                    self._remember_footer(key, start, tail, footer_size)
        return footer_size

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

    def _record_memory_access_locked(self, cache_key):
        self._last_memory_access_ns = max(
            time.time_ns(), self._last_memory_access_ns + 1
        )
        self._memory_access_ns[cache_key] = self._last_memory_access_ns

    def _memory_get(self, cache_key):
        with self._guard:
            content = self._memory_blocks.pop(cache_key, None)
            if content is not None:
                self._memory_blocks[cache_key] = content
                self._record_memory_access_locked(cache_key)
                self._metrics["cache_hits"] += 1
            return content

    def _memory_put(self, cache_key, content):
        if self.max_memory_bytes == 0:
            return
        with self._guard:
            self._memory_blocks.pop(cache_key, None)
            self._memory_blocks[cache_key] = content
            self._record_memory_access_locked(cache_key)
            while (len(self._memory_blocks) > _MAX_MEMORY_EXTENTS
                   or sum(map(len, self._memory_blocks.values()))
                   > self.max_memory_bytes):
                evicted_key, _ = self._memory_blocks.popitem(last=False)
                self._memory_access_ns.pop(evicted_key, None)

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
        with self._guard:
            memory_access = dict(self._memory_access_ns)
        recent_reads = {
            self._block_path(*cache_key): last_used
            for cache_key, last_used in memory_access.items()
        }
        for path in self.directory.iterdir():
            match = _FLAT_CACHE_FILE.fullmatch(path.name)
            if (match is None or match.group("version") != self._version_tag
                    or not match.group("kind").endswith(".block")
                    or path.is_symlink() or not path.is_file()):
                continue
            try:
                stat = path.stat()
                last_used = max(stat.st_mtime_ns, recent_reads.get(path, 0))
                entries.append((last_used, stat.st_size, path))
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
        return self._cat_io(key, url, start, end, total)

    def _cached_extents(self, key, start, end):
        """Read validated on-disk intervals that overlap a requested range."""
        prefix = f"{self._object_name(key)}-"
        extents = []
        with self._guard:
            footer = self._footer_memory.get(key)
            if footer is not None:
                offset, content, _ = footer
                if offset < end and offset + len(content) > start:
                    self._footer_memory.move_to_end(key)
                    self._metrics["cache_hits"] += 1
                    extents.append((offset, offset + len(content), content))
        for path in self.directory.iterdir():
            if path.is_symlink() or not path.is_file() or not path.name.startswith(prefix):
                continue
            match = _EXTENT_SUFFIX.fullmatch(path.name[len(prefix):])
            if match is None:
                continue
            if match.group("kind") == "footer" and footer is not None:
                continue
            offset = int(match.group("start"))
            length = int(match.group("length"))
            if length <= 0 or offset >= end or offset + length <= start:
                continue
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

    def _schedule_io_extents(self, key, url, start, end, total):
        extents = self._cached_extents(key, start, end)
        max_extent = min(_MAX_IO_EXTENT_BYTES, self.max_disk_bytes - _BLOCK_DIGEST_BYTES)
        scheduled = []
        with self._guard:
            for (pending_key, offset, length), future in self._pending.items():
                if pending_key == key and offset < end and offset + length > start:
                    extents.append((offset, offset + length, future))
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
