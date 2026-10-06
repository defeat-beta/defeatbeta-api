import logging
import re
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Callable, Dict, Optional

import duckdb
import pandas as pd

from defeatbeta_api import _print_welcome
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.dataset_cache_fs import (
    DatasetCacheFileSystem, dataset_event_object_id, parquet_metadata_file,
)
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient

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
    def __init__(self, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO,
                 config: Optional[Configuration] = None):
        self.connection = None
        self.http_proxy = http_proxy
        self.config = config if config is not None else Configuration()
        self.log_level = log_level
        self.logger = _console_logger(self.__class__.__name__, log_level)
        self.resolve_cdn_for_uncached_reads = bool(self.config.resolve_cdn_for_uncached_reads)
        self._resolve_ttl = self.config.cdn_url_cache_ttl_seconds
        self._cdn_cache = {}
        self._cdn_lock = Lock()
        self._dataset_cdn_cache = {}
        self._hf_client = HuggingFaceClient(http_proxy=http_proxy)
        self._dataset_fs = None
        self._parquet_indexes = {}
        self._parquet_index_locks = {}
        self._parquet_index_locks_guard = Lock()
        self._prepared_footers = set()
        self._data_update_time = None
        self._footer_index = {}
        self._version_lock = Lock()
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
                logger=self.logger,
            )
            self.connection.register_filesystem(self._dataset_fs)
            try:
                self._dataset_fs.prepare_connections(
                    self._hf_client.get_url_path("stock_prices"), 1
                )
            except Exception as exc:
                self.logger.warning(
                    "Dataset connection prewarm failed (%s); reads will connect on demand",
                    type(exc).__name__,
                )

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
            self._data_update_time = self._hf_client.get_data_update_time()
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

    def _refresh_dataset_version_if_due(self) -> None:
        interval = self.config.cache_version_check_interval_seconds
        if time.monotonic() - self._last_version_check < interval:
            return
        with self._version_lock:
            if time.monotonic() - self._last_version_check < interval:
                return
            version = self._hf_client.get_data_update_time()
            footer_index = self._spec_footer_index()
            self._dataset_fs.update_version(version, footer_index=footer_index)
            self._footer_index = footer_index
            if version != self._data_update_time:
                self._parquet_indexes = {}
                with self._parquet_index_locks_guard:
                    self._parquet_index_locks = {}
                self._prepared_footers = set()
            self._data_update_time = version
            self._last_version_check = time.monotonic()

    def _resolve_one(self, resolve_url: str) -> str:
        """Resolve once per TTL; fall back to the pinned URL on any failure."""
        started_ns = time.perf_counter_ns()
        now = time.monotonic()
        with self._cdn_lock:
            hit = self._cdn_cache.get(resolve_url)
            if hit is not None and now - hit[1] < self._resolve_ttl:
                _record_performance(
                    "duckdb.resolve_url",
                    started_ns,
                    time.perf_counter_ns(),
                    cache_hit=True,
                    status="ok",
                )
                return hit[0]
        try:
            if self.http_proxy is None:
                proxies = None  # requests falls back to environment
            elif self.http_proxy:
                proxies = {"http": self.http_proxy, "https": self.http_proxy}
            else:
                proxies = {"http": None, "https": None}
            cdn_url = self._hf_client.resolve_cdn_url(resolve_url, proxies=proxies)
        except Exception as exc:
            self.logger.warning(
                "CDN resolve failed, using pinned URL: %s",
                redact_signed_urls(str(exc)),
            )
            _record_performance(
                "duckdb.resolve_url",
                started_ns,
                time.perf_counter_ns(),
                cache_hit=False,
                status="fallback",
            )
            return resolve_url
        with self._cdn_lock:
            self._cdn_cache[resolve_url] = (cdn_url, time.monotonic())
        _record_performance(
            "duckdb.resolve_url",
            started_ns,
            time.perf_counter_ns(),
            cache_hit=False,
            status="ok",
        )
        return cdn_url

    def _to_cdn_sql(self, sql: str) -> str:
        started_ns = time.perf_counter_ns()
        rewritten = rewrite_resolve_urls(sql, self._resolve_one)
        _record_performance(
            "duckdb.rewrite_urls",
            started_ns,
            time.perf_counter_ns(),
            changed=rewritten != sql,
        )
        return rewritten

    def _resolve_for_dataset(self, resolve_url: str, refresh: bool = False):
        started_ns = time.perf_counter_ns()
        now = time.monotonic()
        with self._cdn_lock:
            if refresh:
                self._dataset_cdn_cache.pop(resolve_url, None)
            else:
                hit = self._dataset_cdn_cache.get(resolve_url)
                if hit is not None and now - hit[2] < self._resolve_ttl:
                    _record_performance(
                        "duckdb.resolve_url", started_ns, time.perf_counter_ns(),
                        cache_hit=True, status="ok",
                    )
                    return hit[0], hit[1]
        if self.http_proxy is None:
            proxies = None
        elif self.http_proxy:
            proxies = {"http": self.http_proxy, "https": self.http_proxy}
        else:
            proxies = {"http": None, "https": None}
        try:
            url, size = self._hf_client.resolve_cdn_info(resolve_url, proxies=proxies)
        except Exception:
            _record_performance(
                "duckdb.resolve_url", started_ns, time.perf_counter_ns(),
                cache_hit=False, status="error",
            )
            raise
        with self._cdn_lock:
            self._dataset_cdn_cache[resolve_url] = (url, size, time.monotonic())
        _record_performance(
            "duckdb.resolve_url", started_ns, time.perf_counter_ns(),
            cache_hit=False, status="ok",
        )
        return url, size

    def _load_or_build_parquet_index(self, url, path=None):
        path = path or self._dataset_fs.register(url)
        key = path
        guard = getattr(self, "_parquet_index_locks_guard", None)
        if guard is None:
            guard = self._parquet_index_locks_guard = Lock()
            self._parquet_index_locks = {}
        with guard:
            lock = self._parquet_index_locks.setdefault(key, Lock())
        with lock:
            chunks = self._parquet_indexes.get(key)
            if chunks is not None:
                return chunks
            self._dataset_fs.prepare_footer(path)
            footer_bytes = self._dataset_fs.cached_footer_bytes(path)
            with parquet_metadata_file(footer_bytes) as metadata_path:
                with self._get_cursor() as cursor:
                    chunks = cursor.execute(
                        "SELECT row_group_id, path_in_schema, stats_min_value, "
                        "stats_max_value, "
                        "COALESCE(dictionary_page_offset, data_page_offset), "
                        "total_compressed_size FROM parquet_metadata(?)",
                        [metadata_path],
                    ).fetchall()
            self._parquet_indexes[key] = chunks
            prepared = getattr(self, "_prepared_footers", None)
            if prepared is None:
                prepared = self._prepared_footers = set()
            prepared.add(key)
            return chunks

    def _to_dataset_sql(self, sql: str) -> str:
        registered = {}

        def register(url):
            path = self._dataset_fs.register(url)
            registered[url] = path
            return path

        rewritten = rewrite_dataset_urls(sql, register)
        scan = _simple_symbol_scan(sql)
        for url, path in registered.items():
            if not url.endswith(".parquet"):
                continue
            started_ns = time.perf_counter_ns()
            status = "ok"
            ranges = []
            try:
                if (scan is not None and scan[0] == url
                        and getattr(getattr(self, "config", None),
                                    "cache_symbol_column_chunk_prefetch", True)):
                    _, symbol, columns = scan
                    chunks = getattr(self, "_parquet_indexes", {}).get(path)
                    if chunks is None:
                        if getattr(getattr(self, "config", None), "cache_prepare_footer_on_first_use", True):
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
                elif getattr(getattr(self, "config", None), "cache_prepare_footer_on_first_use", True):
                    prepared = getattr(self, "_prepared_footers", set())
                    key = path
                    if key not in prepared:
                        self._dataset_fs.prepare_footer(path)
                        prepared.add(key)
                        self._prepared_footers = prepared
            except Exception as exc:
                status = "error"
                logger = getattr(self, "logger", None)
                if logger is not None:
                    logger.warning(
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
                    self._dataset_fs.prefetch_ranges(path, ranges)
                except Exception as exc:
                    prefetch_status = "error"
                    logger = getattr(self, "logger", None)
                    if logger is not None:
                        logger.warning(
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

    def _invalidate_resolved_urls(self, sql: str) -> None:
        resolve_urls = set(_RESOLVE_URL_RE.findall(sql))
        with self._cdn_lock:
            for resolve_url in resolve_urls:
                self._cdn_cache.pop(resolve_url, None)
                if hasattr(self, "_dataset_cdn_cache"):
                    self._dataset_cdn_cache.pop(resolve_url, None)

    @contextmanager
    def _get_cursor(self):
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def _execute_query(self, sql: str, use_dataset_cache: bool = False) -> pd.DataFrame:
        self.logger.debug(f"Executing query: {redact_signed_urls(sql)}")
        started_ns = time.perf_counter_ns()
        cursor_opened_ns = started_ns
        prepared_ns = started_ns
        materialized_ns = started_ns
        ended_ns = started_ns
        status = "error"
        result = None
        cache_before = self._dataset_fs.metrics() if use_dataset_cache else None
        range_event_offset = (
            self._dataset_fs.range_event_sequence() if use_dataset_cache else 0
        )
        read_event_offset = (
            self._dataset_fs.read_event_sequence() if use_dataset_cache else 0
        )
        try:
            if use_dataset_cache:
                sql = self._to_dataset_sql(sql)
                prepared_ns = time.perf_counter_ns()
            with self._get_cursor() as cursor:
                cursor_opened_ns = time.perf_counter_ns()
                result = cursor.sql(sql).df()
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
                cache_after = self._dataset_fs.metrics()
                range_events, ranges_complete = self._dataset_fs.range_event_snapshot(
                    range_event_offset
                )
                read_events, reads_complete = self._dataset_fs.read_event_snapshot(
                    read_event_offset
                )
                _record_performance(
                    "duckdb.dataset_cache.prepare", started_ns, prepared_ns
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
                ("duckdb.cursor.open", prepared_ns, cursor_opened_ns, {}),
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

    def query(self, sql: str) -> pd.DataFrame:
        started_ns = time.perf_counter_ns()
        status = "error"
        original_sql = sql
        if (getattr(self, "_dataset_fs", None) is not None
                and _DATASET_URL_RE.search(sql)):
            try:
                self._refresh_dataset_version_if_due()
                result = self._execute_query(original_sql, use_dataset_cache=True)
                _record_performance(
                    "duckdb.query", started_ns, time.perf_counter_ns(),
                    status="dataset_cache",
                )
                return result
            except Exception as dataset_error:
                self.logger.warning(
                    "Dataset cache query failed, retrying original transport: %s",
                    redact_signed_urls(str(dataset_error)),
                )
        rewritten_sql = self._to_cdn_sql(sql) if self.resolve_cdn_for_uncached_reads else sql
        try:
            result = self._execute_query(rewritten_sql)
            status = "ok"
            return result
        except Exception as direct_error:
            if rewritten_sql != original_sql:
                self._invalidate_resolved_urls(original_sql)
                self.logger.warning(
                    "CDN query failed, retrying pinned URL: %s",
                    redact_signed_urls(str(direct_error)),
                )
                try:
                    result = self._execute_query(original_sql)
                    status = "fallback"
                    return result
                except Exception as fallback_error:
                    error = fallback_error
            else:
                error = direct_error
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
        if getattr(self, "_dataset_fs", None) is not None:
            self._dataset_fs.close()
            self._dataset_fs = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
