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
from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
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
_PRICE_PREFETCH_RE = re.compile(
    rf"^\s*SELECT\s+\*\s+FROM\s+'({_RESOLVE_URL_RE.pattern})'\s+WHERE\s+symbol\s*=",
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
    """Route the project's Parquet and JSON readers through its block cache."""
    rewritten = rewrite_resolve_urls(sql, register, suppress_errors=False)

    def _json_reader(match):
        path = register(match.group(2)).replace("'", "''")
        return f"{match.group(1)}'{path}'"

    return _READ_JSON_URL_RE.sub(_json_reader, rewritten)

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
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s %(threadName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        self.resolve_direct = bool(self.config.resolve_direct)
        self._resolve_ttl = self.config.resolve_ttl_seconds
        self._cdn_cache = {}
        self._cdn_lock = Lock()
        self._dataset_cdn_cache = {}
        self._hf_client = HuggingFaceClient(http_proxy=http_proxy)
        self._dataset_fs = None
        self._data_update_time = None
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
                block_size=self.config.cache_block_size,
                max_disk_bytes=self.config.cache_max_disk_bytes,
                max_memory_blocks=self.config.cache_max_memory_blocks,
                workers=self.config.cache_workers,
                timeout=self.config.http_timeout,
            )
            self.connection.register_filesystem(self._dataset_fs)

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

    def _refresh_dataset_version_if_due(self) -> None:
        interval = self.config.cache_version_check_seconds
        if time.monotonic() - self._last_version_check < interval:
            return
        with self._version_lock:
            if time.monotonic() - self._last_version_check < interval:
                return
            version = self._hf_client.get_data_update_time()
            self._dataset_fs.update_version(version)
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

    def _to_dataset_sql(self, sql: str) -> str:
        registered = {}

        def register(url):
            path = self._dataset_fs.register(url)
            registered[url] = path
            return path

        rewritten = rewrite_dataset_urls(sql, register)
        price = _PRICE_PREFETCH_RE.match(sql)
        if price and price.group(1).endswith("/stock_prices.parquet"):
            self._dataset_fs.prefetch(registered[price.group(1)])
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
                _record_performance(
                    "duckdb.dataset_cache.prepare", started_ns, prepared_ns
                )
                _record_performance(
                    "duckdb.dataset_cache.io", prepared_ns, materialized_ns,
                    **{
                        key: cache_after[key] - cache_before[key]
                        for key in cache_before
                    },
                    ranges=self._dataset_fs.range_events(since=range_event_offset),
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
        rewritten_sql = self._to_cdn_sql(sql) if self.resolve_direct else sql
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
