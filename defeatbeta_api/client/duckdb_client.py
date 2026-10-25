import atexit
import logging
import math
import os
import re
import sys
import time
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Callable, Dict, Optional
from weakref import WeakValueDictionary

import duckdb
import pandas as pd

from defeatbeta_api import _print_welcome
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.dataset_cache_fs import (
    DatasetCacheFileSystem, DatasetNetworkFileSystem, DatasetVersionChanged,
    dataset_event_object_id, parquet_metadata_file,
)
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.client.shared_resources import RESOLVED_URLS, SharedCache, dataset_file_identity, network_identity

# Pinned Parquet URLs. DuckDB re-resolves the 302 on every range request, so
# cold queries pay the redirect cost repeatedly. Resolve only Parquet inputs:
# JSON and other readers have different URL/glob semantics.
_RESOLVE_URL_RE = re.compile(
    r"https://huggingface\.co/datasets/defeatbeta/yahoo-finance-data/resolve/[^\s'\"]+\.parquet"
)
_DATASET_URL_RE = re.compile(
    r"https://huggingface\.co/datasets/defeatbeta/yahoo-finance-data/resolve/[^\s'\"]+\.(?:parquet|json)"
)
_READ_JSON_URL_RE = re.compile(
    rf"(read_json(?:_auto)?\s*\(\s*)'({_DATASET_URL_RE.pattern})'",
    re.IGNORECASE,
)
_FROM_URL_RE = re.compile(
    rf"(FROM|JOIN)\s+'({_RESOLVE_URL_RE.pattern})'",
    re.IGNORECASE,
)
_READ_PARQUET_URL_RE = re.compile(
    rf"read_parquet\s*\(\s*'({_RESOLVE_URL_RE.pattern})'\s*\)",
    re.IGNORECASE,
)
_SIGNED_URL_RE = re.compile(r"(https?://[^\s'\"?]+)\?[^\s'\"]*")
_SIMPLE_SYMBOL_SCAN_RE = re.compile(
    rf"^\s*SELECT\s+(?P<columns>.*?)\s+FROM\s+'(?P<url>{_RESOLVE_URL_RE.pattern})'"
    rf"\s+WHERE\s+symbol\s*=\s*'(?P<symbol>[A-Za-z0-9._^-]+)'(?P<tail>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_SIMPLE_COLUMN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SIMPLE_ORDER_RE = re.compile(
    r"(?P<column>[A-Za-z_][A-Za-z0-9_]*)(?:\s+(?:ASC|DESC))?",
    re.IGNORECASE,
)


def _process_cpu_count():
    """CPUs this process may run on, honoring affinity where the OS exposes it."""
    if hasattr(os, "process_cpu_count"):
        return os.process_cpu_count()
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count()


def _cgroup_cpu_quota(root):
    """CPU quota from cgroup v2 or v1 limits, or None when unlimited or unknown."""
    candidates = [("cpu.max", None)] + [
        (f"{folder}/cpu.cfs_quota_us", f"{folder}/cpu.cfs_period_us")
        for folder in ("cpu", "cpu,cpuacct")
    ]
    for quota_name, period_name in candidates:
        try:
            if period_name is None:
                quota, period = Path(root, quota_name).read_text().split()
            else:
                quota = Path(root, quota_name).read_text().strip()
                period = Path(root, period_name).read_text().strip()
            quota, period = int(quota), int(period)
        except (OSError, ValueError):
            continue
        if quota > 0 and period > 0:
            return math.ceil(quota / period)
    return None


def available_cpu_count(cgroup_root="/sys/fs/cgroup"):
    """CPUs usable by this process: affinity, then any container CPU quota."""
    count = _process_cpu_count() or 1
    quota = _cgroup_cpu_quota(cgroup_root)
    return max(1, min(count, quota) if quota else count)


# Cached dataset queries are CPU-bound and DuckDB runs each one on its calling
# thread, so running more of them at once than there are CPUs only adds
# contention. Network-bound queries are not limited.
_QUERY_SLOTS = BoundedSemaphore(available_cpu_count())


def _reset_query_slots():
    global _QUERY_SLOTS
    _QUERY_SLOTS = BoundedSemaphore(available_cpu_count())


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_query_slots)


def redact_signed_urls(text: str) -> str:
    """Strip URL query strings so logs never persist signed parameters."""
    return _SIGNED_URL_RE.sub(r"\1?<redacted>", text)


def rewrite_resolve_urls(sql: str, resolve, *, suppress_errors: bool = True) -> str:
    """Replace pinned Parquet URLs; optionally retain originals on failure.

    Exact file-list syntax avoids treating signed query strings as glob
    patterns. Non-Parquet URLs are deliberately left unchanged.
    """

    def _resolve_url(resolve_url):
        try:
            return resolve(resolve_url)
        except Exception:
            if not suppress_errors:
                raise
            return resolve_url

    def _reader(match):
        resolve_url = match.group(1)
        cdn_url = _resolve_url(resolve_url)
        if cdn_url == resolve_url:
            return match.group(0)
        escaped = cdn_url.replace("'", "''")
        return f"read_parquet(['{escaped}'])"

    sql = _READ_PARQUET_URL_RE.sub(_reader, sql)

    def _from(match):
        resolve_url = match.group(2)
        cdn_url = _resolve_url(resolve_url)
        if cdn_url == resolve_url:
            return match.group(0)
        escaped = cdn_url.replace("'", "''")
        return f"{match.group(1)} read_parquet(['{escaped}'])"

    return _FROM_URL_RE.sub(_from, sql)


def rewrite_dataset_urls(sql: str, register) -> str:
    """Route the project's Parquet and JSON readers through its range cache."""
    rewritten = rewrite_resolve_urls(sql, register, suppress_errors=False)

    def _json_reader(match):
        path = register(match.group(2)).replace("'", "''")
        return f"{match.group(1)}'{path}'"

    return _READ_JSON_URL_RE.sub(_json_reader, rewritten)


def _simple_symbol_scan(sql):
    match = _SIMPLE_SYMBOL_SCAN_RE.fullmatch(sql)
    if match is None:
        return None
    projection = match.group("columns").strip()
    if projection == "*":
        columns = None
    else:
        projected = [part.strip() for part in projection.split(",")]
        if not projected or any(_SIMPLE_COLUMN_RE.fullmatch(part) is None
                                for part in projected):
            return None
        columns = {part.lower() for part in projected}
        columns.add("symbol")
    tail = match.group("tail").strip().removesuffix(";").strip()
    if tail:
        order = re.fullmatch(r"ORDER\s+BY\s+(.+)", tail, re.IGNORECASE | re.DOTALL)
        if order is None:
            return None
        for part in order.group(1).split(","):
            item = _SIMPLE_ORDER_RE.fullmatch(part.strip())
            if item is None:
                return None
            if columns is not None:
                columns.add(item.group("column").lower())
    return match.group("url"), match.group("symbol"), columns


def plan_symbol_column_chunks(chunks, symbol, columns=None):
    """Plan conservative, row-group-local byte ranges from Parquet footer metadata.

    Each row is (row_group_id, column_path, min, max, chunk_start, chunk_size).
    Missing symbol statistics include the row group rather than risking a false skip.
    """
    groups = {}
    for group_id, column, lower, upper, start, size in chunks:
        group = groups.setdefault(group_id, {"symbol": None, "ranges": []})
        if column == "symbol":
            group["symbol"] = (lower, upper)
        selected = columns is None or column.split(".", 1)[0].lower() in columns
        if (selected and isinstance(start, int) and isinstance(size, int)
                and start >= 0 and size > 0):
            group["ranges"].append((start, start + size))

    planned = []
    for group_id in sorted(groups):
        group = groups[group_id]
        bounds = group["symbol"]
        if bounds is None:
            continue
        lower, upper = bounds
        if (isinstance(lower, str) and isinstance(upper, str)
                and lower <= upper and not lower <= symbol <= upper):
            continue
        for start, end in sorted(group["ranges"]):
            if planned and planned[-1][2] == group_id and start <= planned[-1][1]:
                planned[-1] = (planned[-1][0], max(end, planned[-1][1]), group_id)
            else:
                planned.append((start, end, group_id))
    return [(start, end) for start, end, _ in planned]

_instances = {}
_lock = Lock()
_performance_recorder = ContextVar("defeatbeta_performance_recorder", default=None)


def _close_shared_duckdb_clients():
    """Release registered filesystems before native bindings are finalized."""
    with _lock:
        clients = list(_instances.values())
        _instances.clear()
    first_error = None
    for client in clients:
        try:
            client.close()
        except BaseException as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


@contextmanager
def capture_performance(recorder: Callable[[Dict], None]):
    """Capture opt-in client timing events in the current execution context."""
    token = _performance_recorder.set(recorder)
    try:
        yield
    finally:
        _performance_recorder.reset(token)


def _record_performance(name: str, started_ns: int, ended_ns: int, **details) -> None:
    recorder = _performance_recorder.get()
    if recorder is None:
        return
    event = {
        "name": name,
        "started_ns": started_ns,
        "ended_ns": ended_ns,
        "duration_ns": max(0, ended_ns - started_ns),
        **details,
    }
    try:
        recorder(event)
    except Exception:
        # Diagnostics must never change query behavior.
        return


def _config_key(config: Configuration):
    return tuple(sorted(vars(config).items()))


class _CurrentStdoutHandler(logging.StreamHandler):
    def emit(self, record):
        self.stream = sys.stdout
        super().emit(record)


def _console_logger(name, level):
    """Keep API diagnostics visible without changing the host application's logs."""
    effective_level = logging.INFO if level is None else level
    level_name = (
        logging.getLevelName(effective_level)
        if isinstance(effective_level, int) else str(effective_level).upper()
    )
    parent = logging.getLogger(name)
    parent.propagate = False
    logger = logging.getLogger(f"{name}.{level_name}")
    logger.setLevel(effective_level)
    if not any(isinstance(handler, _CurrentStdoutHandler) for handler in logger.handlers):
        handler = _CurrentStdoutHandler()
        handler.setFormatter(logging.Formatter(
            f'%(asctime)s %(levelname)s {name} %(threadName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)
    return logger


def get_duckdb_client(http_proxy=None, log_level=None, config=None):
    effective_config = config if config is not None else Configuration()
    key = (http_proxy, log_level, _config_key(effective_config))
    with _lock:
        client = _instances.get(key)
        if client is None or client.connection is None:
            client = DuckDBClient(http_proxy, log_level, effective_config)
            _instances[key] = client
        return client


class DuckDBClient:
    _version_check_running = False

    def __init__(self, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO,
                 config: Optional[Configuration] = None):
        self.connection = None
        self.http_proxy = http_proxy
        self.config = config if config is not None else Configuration()
        self.log_level = log_level
        self.logger = _console_logger(self.__class__.__name__, log_level)
        self._resolve_ttl = self.config.cdn_url_cache_ttl_seconds
        self._cdn_lock = Lock()
        self._dataset_cdn_cache = {}
        self._hf_client = HuggingFaceClient(http_proxy=http_proxy)
        self._dataset_fs = None
        self._parquet_indexes = WeakValueDictionary()
        self._parquet_index_locks = {}
        self._parquet_index_locks_guard = Lock()
        self._prepared_footers = set()
        self._data_update_time = None
        self._footer_index = {}
        self._version_lock = Lock()
        self._dataset_generation = 0
        self._catalog_cache = SharedCache()
        self._last_version_check = 0.0
        self._initialize_connection()
        self._load_dataset_version()
        self._last_version_check = time.monotonic()
        if self.config.cache_enabled:
            self._dataset_fs = DatasetCacheFileSystem(
                directory=self.config.get_cache_directory(),
                version=self._data_update_time,
                resolve=self._resolve_for_dataset,
                http_proxy=http_proxy,
                max_disk_bytes=self.config.cache_data_disk_limit_bytes,
                max_memory_bytes=self.config.cache_data_memory_limit_bytes,
                workers=self.config.cache_fetch_workers,
                timeout=self.config.cache_http_timeout_seconds,
                network_chunk_size=self.config.cache_range_split_bytes,
                footer_index=self._footer_index,
            )
            self.connection.register_filesystem(self._dataset_fs)
        self._uncached_fs = None
        self._network_fs_lock = Lock()

    def _get_uncached_filesystem(self):
        with self._version_lock, self._network_fs_lock:
            if self._uncached_fs is None:
                filesystem = DatasetNetworkFileSystem(
                    directory=str(self.config.cache_directory or "."),
                    version=self._data_update_time, resolve=self._resolve_for_dataset,
                    http_proxy=self.http_proxy, timeout=self.config.cache_http_timeout_seconds,
                    footer_index=self._footer_index, cache_enabled=False,
                )
                try:
                    self.connection.register_filesystem(filesystem)
                except BaseException:
                    filesystem.close()
                    raise
                self._uncached_fs = filesystem
            return self._uncached_fs

    def _initialize_connection(self) -> None:
        started_ns = time.perf_counter_ns()
        status = "ok"
        try:
            self.connection = duckdb.connect(":memory:")
            self.logger.debug("DuckDB connection initialized.")

            duckdb_settings = self.config.get_duckdb_settings()
            if self.http_proxy:
                escaped_proxy = self.http_proxy.replace("'", "''")
                duckdb_settings.insert(
                    0, f"SET GLOBAL http_proxy = '{escaped_proxy}';"
                )

            if self.log_level and self.log_level == logging.DEBUG:
                duckdb_settings.append("CALL enable_logging('HTTP', level = 'DEBUG', storage = 'stdout')")

            for query in duckdb_settings:
                displayed = (
                    "SET GLOBAL http_proxy = '<redacted>'"
                    if query.startswith("SET GLOBAL http_proxy") else query
                )
                self.logger.debug("DuckDB settings: %s", displayed)
                self.connection.execute(query)
        except Exception as e:
            status = "error"
            self.logger.error(f"Failed to initialize connection: {str(e)}")
            raise
        finally:
            _record_performance(
                "duckdb.initialize_connection",
                started_ns,
                time.perf_counter_ns(),
                status=status,
            )

    def _load_dataset_version(self):
        """Use the remote data version in all dataset block-cache keys."""
        started_ns = time.perf_counter_ns()
        status = "ok"
        try:
            self._data_update_time = self._hf_client.get_shared_data_update_time(
                self.config.cache_version_check_interval_seconds)
            self._footer_index = self._spec_footer_index()
            _print_welcome(self._data_update_time)
        except Exception as e:
            status = "error"
            self.logger.error(f"Failed to load dataset version: {str(e)}")
            raise
        finally:
            _record_performance(
                "duckdb.load_dataset_version",
                started_ns,
                time.perf_counter_ns(),
                status=status,
            )

    def _spec_footer_index(self):
        spec = getattr(self._hf_client, "dataset_spec", None)
        index = spec.get("footer_index") if isinstance(spec, dict) else None
        return dict(index) if isinstance(index, dict) else {}

    def _refresh_dataset_version_if_due(self, *, use_dataset_cache=True) -> int:
        interval = self.config.cache_version_check_interval_seconds
        with self._version_lock:
            # One caller checks the remote version; others keep the current one.
            due = (not self._version_check_running
                   and time.monotonic() - self._last_version_check >= interval)
            if due:
                self._version_check_running = True
        fetched = None
        if due:
            # Never hold the version lock across network I/O: cache reads
            # resolve URLs under it and must not wait for spec.json.
            try:
                fetched = (self._hf_client.get_shared_data_update_time(interval),
                           self._spec_footer_index())
            except Exception as exc:
                self.logger.warning(
                    "Dataset version check failed; keeping version %s: %s",
                    self._data_update_time, redact_signed_urls(str(exc)))
        try:
            with self._version_lock:
                version, footer_index = fetched or (self._data_update_time, self._footer_index)
                if version != self._data_update_time or footer_index != self._footer_index:
                    # Adopt the remote version before touching either reader, so
                    # active queries are invalidated even if the disk-cache
                    # transition fails and the network reader can still follow.
                    self._dataset_generation += 1
                    self._parquet_indexes = type(self._parquet_indexes)()
                    with self._parquet_index_locks_guard:
                        self._parquet_index_locks = {}
                    self._prepared_footers = set()
                self._data_update_time, self._footer_index = version, footer_index
                # Synchronize only the reader this query will use. A failed disk
                # cache must not prevent network fallback, and a recovered reader
                # must catch up even before the next remote metadata check is due.
                filesystem = (self._dataset_fs if use_dataset_cache
                              else self._uncached_fs)
                if filesystem is not None and (
                        fetched is not None or filesystem.version != version
                        or filesystem._footer_index != footer_index):
                    filesystem.update_version(version, footer_index=footer_index)
                return self._dataset_generation
        finally:
            if due:
                with self._version_lock:
                    # A failed check is retried after the normal interval.
                    self._last_version_check = time.monotonic()
                    self._version_check_running = False

    def _resolve_for_dataset(self, resolve_url: str, refresh: bool = False):
        started_ns = time.perf_counter_ns()
        with self._version_lock, self._cdn_lock:
            version = self._data_update_time
            file_identity = dataset_file_identity(version, resolve_url, self._footer_index)
            previous = self._dataset_cdn_cache.get(resolve_url)
            # Local state only identifies the value a forced refresh replaces.
            # All reads use the shared cache's version and routing identity.
        if self.http_proxy is None:
            proxies = None
        elif self.http_proxy:
            proxies = {"http": self.http_proxy, "https": self.http_proxy}
        else:
            proxies = {"http": None, "https": None}
        built = False
        try:
            def build():
                nonlocal built
                built = True
                url, size = self._hf_client.resolve_cdn_info(resolve_url, proxies=proxies)
                return url, size, time.monotonic()

            identity = (network_identity(resolve_url, self.http_proxy), file_identity)
            observed = previous[1] if previous is not None and previous[0] == identity else None
            url, size, resolved_at = RESOLVED_URLS.get_or_build(
                identity, build, force_if=observed if refresh else None,
                valid=lambda item: time.monotonic() - item[2] < self._resolve_ttl)
        except Exception:
            _record_performance(
                "duckdb.resolve_url", started_ns, time.perf_counter_ns(),
                cache_hit=False, status="error",
            )
            raise
        with self._version_lock, self._cdn_lock:
            current = self._dataset_cdn_cache.get(resolve_url)
            current_identity = dataset_file_identity(
                self._data_update_time, resolve_url, self._footer_index)
            if (file_identity == current_identity
                    and (current is None or current[1][2] <= resolved_at)):
                self._dataset_cdn_cache[resolve_url] = (identity, (url, size, resolved_at))
        _record_performance(
            "duckdb.resolve_url", started_ns, time.perf_counter_ns(),
            cache_hit=not built, status="ok",
        )
        return url, size

    def _load_or_build_parquet_index(self, url, path=None):
        path = path or self._dataset_fs.register(url)
        key = path
        with self._parquet_index_locks_guard:
            lock = self._parquet_index_locks.setdefault(key, Lock())
        with lock:
            chunks = self._parquet_indexes.get(key)
            if chunks is not None:
                return chunks
            self._dataset_fs.prepare_footer(path)
            footer_bytes = self._dataset_fs.cached_footer_bytes(path)
            def build():
                with parquet_metadata_file(footer_bytes) as metadata_path:
                    with self._get_cursor() as cursor:
                        return cursor.execute(
                            "SELECT row_group_id, path_in_schema, stats_min_value, "
                            "stats_max_value, "
                            "COALESCE(dictionary_page_offset, data_page_offset), "
                            "total_compressed_size FROM parquet_metadata(?)",
                            [metadata_path],
                        ).fetchall()

            chunks = self._dataset_fs.shared_parquet_index(path, footer_bytes, build)
            self._parquet_indexes[key] = chunks
            self._prepared_footers.add(key)
            return chunks

    def _to_dataset_sql(self, sql: str, filesystem=None) -> str:
        filesystem = filesystem if filesystem is not None else self._dataset_fs
        registered = {}

        def register(url):
            path = filesystem.register(url)
            registered[url] = path
            return path

        rewritten = rewrite_dataset_urls(sql, register)
        if not getattr(filesystem, "cache_enabled", True):
            return rewritten
        scan = _simple_symbol_scan(sql)
        for url, path in registered.items():
            if not url.endswith(".parquet"):
                continue
            started_ns = time.perf_counter_ns()
            status = "ok"
            ranges = []
            try:
                if (scan is not None and scan[0] == url
                        and self.config.cache_symbol_column_chunk_prefetch):
                    _, symbol, columns = scan
                    chunks = self._parquet_indexes.get(path)
                    if chunks is None:
                        if self.config.cache_prepare_footer_on_first_use:
                            chunks = self._load_or_build_parquet_index(url, path)
                        else:
                            with self._get_cursor() as cursor:
                                chunks = cursor.execute(
                                    "SELECT row_group_id, path_in_schema, stats_min_value, "
                                    "stats_max_value, "
                                    "COALESCE(dictionary_page_offset, data_page_offset), "
                                    "total_compressed_size FROM parquet_metadata(?)",
                                    [path],
                                ).fetchall()
                    ranges = plan_symbol_column_chunks(chunks, symbol, columns)
                elif self.config.cache_prepare_footer_on_first_use:
                    if path not in self._prepared_footers:
                        filesystem.prepare_footer(path)
                        self._prepared_footers.add(path)
            except Exception as exc:
                status = "error"
                self.logger.warning(
                    "Parquet metadata preparation failed (%s); using demand reads",
                    type(exc).__name__,
                )
            finally:
                _record_performance(
                    "duckdb.prepare_parquet_metadata", started_ns,
                    time.perf_counter_ns(), file=url.rsplit("/", 1)[-1],
                    status=status,
                )
            if ranges:
                prefetch_started_ns = time.perf_counter_ns()
                prefetch_status = "ok"
                try:
                    filesystem.prefetch_ranges(path, ranges)
                except Exception as exc:
                    prefetch_status = "error"
                    self.logger.warning(
                        "Parquet range prefetch failed (%s); using demand reads",
                        type(exc).__name__,
                    )
                finally:
                    _record_performance(
                        "duckdb.prefetch_ranges", prefetch_started_ns,
                        time.perf_counter_ns(), file=url.rsplit("/", 1)[-1],
                        object_id=dataset_event_object_id(url),
                        status=prefetch_status, ranges=len(ranges),
                        planned_intervals=ranges,
                    )
        return rewritten

    @contextmanager
    def _get_cursor(self):
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def _execute_query(self, sql: str, use_dataset_cache: bool = False, filesystem=None) -> pd.DataFrame:
        filesystem = filesystem if filesystem is not None else self._dataset_fs
        self.logger.debug(f"Executing query: {redact_signed_urls(sql)}")
        started_ns = time.perf_counter_ns()
        cursor_opened_ns = started_ns
        prepared_ns = started_ns
        slot_acquired_ns = started_ns
        materialized_ns = started_ns
        ended_ns = started_ns
        status = "error"
        result = None
        cache_before = filesystem.metrics() if use_dataset_cache else None
        range_event_offset = (
            filesystem.range_event_sequence() if use_dataset_cache else 0
        )
        read_event_offset = (
            filesystem.read_event_sequence() if use_dataset_cache else 0
        )
        try:
            if use_dataset_cache:
                sql = self._to_dataset_sql(sql, filesystem)
                prepared_ns = slot_acquired_ns = time.perf_counter_ns()
            # Prefetches are scheduled above, so queued queries still download.
            limited = use_dataset_cache and filesystem is self._dataset_fs
            with _QUERY_SLOTS if limited else nullcontext():
                slot_acquired_ns = time.perf_counter_ns()
                with self._get_cursor() as cursor:
                    cursor_opened_ns = time.perf_counter_ns()
                    cursor.execute(sql)
                    result = cursor.fetchdf()
                    materialized_ns = time.perf_counter_ns()
            ended_ns = time.perf_counter_ns()
            status = "ok"
        finally:
            if ended_ns == started_ns:
                ended_ns = time.perf_counter_ns()
                if materialized_ns == started_ns:
                    materialized_ns = ended_ns
            rows = len(result) if result is not None else 0
            if use_dataset_cache:
                cache_after = filesystem.metrics()
                range_events, ranges_complete = filesystem.range_event_snapshot(
                    range_event_offset
                )
                read_events, reads_complete = filesystem.read_event_snapshot(
                    read_event_offset
                )
                _record_performance(
                    "duckdb.dataset_cache.prepare", started_ns, prepared_ns
                )
                _record_performance(
                    "duckdb.query_slot.wait", prepared_ns, slot_acquired_ns
                )
                _record_performance(
                    "duckdb.dataset_cache.io", prepared_ns, materialized_ns,
                    **{
                        key: cache_after[key] - cache_before[key]
                        for key in cache_before
                    },
                    ranges=range_events, reads=read_events,
                    ranges_complete=ranges_complete,
                    reads_complete=reads_complete,
                )
            events = (
                ("duckdb.cursor.open", slot_acquired_ns, cursor_opened_ns, {}),
                ("duckdb.sql_to_dataframe", cursor_opened_ns, materialized_ns, {"rows": rows}),
                ("duckdb.cursor.close", materialized_ns, ended_ns, {}),
                ("duckdb.execute_query", started_ns, ended_ns, {"status": status, "rows": rows}),
            )
            for name, event_start, event_end, details in events:
                _record_performance(name, event_start, event_end, **details)
        duration = (ended_ns - started_ns) / 1e9
        self.logger.debug(
            f"Query executed successfully. Rows returned: {len(result)}. Cost: {duration:.2f} seconds.")
        return result

    def _query_dataset(self, sql, *, use_dataset_cache=True):
        """Validate the whole result; retry once if another query updates data.

        No lock is held across SQL execution. The generation check
        also covers cache-only reads and exceptions wrapped by DuckDB.
        """
        for attempt in range(2):
            generation = self._refresh_dataset_version_if_due(
                use_dataset_cache=use_dataset_cache)
            try:
                if use_dataset_cache:
                    result = self._execute_query(sql, use_dataset_cache=True)
                else:
                    result = self._execute_query(
                        sql, use_dataset_cache=True, filesystem=self._get_uncached_filesystem())
            except Exception:
                with self._version_lock:
                    if generation == self._dataset_generation:
                        raise
            else:
                with self._version_lock:
                    if generation == self._dataset_generation:
                        return result
            if attempt == 0:
                self.logger.debug("Dataset changed during query; retrying the complete query")
        raise DatasetVersionChanged("Dataset changed during both query attempts; retry the query")

    def _get_data_update_time(self) -> str:
        """Use the active query version and the existing refresh interval."""
        self._refresh_dataset_version_if_due(use_dataset_cache=self.config.cache_enabled)
        with self._version_lock:
            return self._data_update_time

    def _query_catalog(self, sql: str) -> pd.DataFrame:
        """Share typed scalar catalog rows, returning an isolated DataFrame.

        CompanyMeta alone uses this cache; arbitrary user SQL is not memoized.
        Dataset generations and the complete SQL separate versions and schemas.
        """
        cache = self._catalog_cache
        if not self.config.cache_enabled or cache is None:
            return self.query(sql)
        for _ in range(2):
            generation = self._refresh_dataset_version_if_due()

            def build():
                frame = self.query(sql)
                with self._version_lock:
                    if generation != self._dataset_generation:
                        raise DatasetVersionChanged("Dataset changed while loading the company catalog")
                # Keep shared-cache sentinel comparisons independent of DataFrame equality.
                return (frame,)

            try:
                catalog = cache.get_or_build(
                    (generation, sql), build,
                    weight=lambda value: int(value[0].memory_usage(index=True, deep=True).sum()),
                )
                result = catalog[0].copy(deep=True)
            except Exception:
                with self._version_lock:
                    if generation == self._dataset_generation:
                        raise
            else:
                with self._version_lock:
                    if generation == self._dataset_generation:
                        return result
        raise DatasetVersionChanged("Dataset changed during both catalog attempts; retry the query")

    def query(self, sql: str) -> pd.DataFrame:
        started_ns = time.perf_counter_ns()
        status = "error"
        original_sql = sql
        if (self._dataset_fs is not None
                and _DATASET_URL_RE.search(sql)):
            try:
                result = self._query_dataset(original_sql)
                _record_performance(
                    "duckdb.query", started_ns, time.perf_counter_ns(),
                    status="dataset_cache",
                )
                return result
            except DatasetVersionChanged:
                raise
            except Exception as dataset_error:
                self.logger.warning(
                    "Dataset cache query failed, retrying without the local cache: %s",
                    redact_signed_urls(str(dataset_error)),
                )
        if _DATASET_URL_RE.search(sql):
            try:
                return self._query_dataset(original_sql, use_dataset_cache=False)
            except DatasetVersionChanged:
                raise
            except Exception as error:
                message = redact_signed_urls(str(error))
                raise Exception(f"Query failed: {message}") from error
        try:
            result = self._execute_query(sql)
            status = "ok"
            return result
        except Exception as error:
            message = redact_signed_urls(str(error))
            self.logger.error(f"Query failed: {message}")
            raise Exception(f"Query failed: {message}")
        finally:
            _record_performance(
                "duckdb.query",
                started_ns,
                time.perf_counter_ns(),
                status=status,
            )

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.logger.debug("DuckDB connection closed.")
            self.connection = None
        self._catalog_cache = None
        if getattr(self, "_dataset_fs", None) is not None:
            self._dataset_fs.close()
            self._dataset_fs = None
        if getattr(self, "_uncached_fs", None) is not None:
            self._uncached_fs.close()
            self._uncached_fs = None
        if getattr(self, "_hf_client", None) is not None:
            self._hf_client.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Imported network resources register earlier; atexit runs callbacks in reverse.
atexit.register(_close_shared_duckdb_clients)
