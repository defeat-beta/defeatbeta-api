import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Callable, Dict, Optional

import duckdb
import pandas as pd

from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient

# Pinned Parquet URLs. DuckDB re-resolves the 302 on every range request, so
# cold queries pay the redirect cost repeatedly. Resolve only Parquet inputs:
# JSON and other readers have different URL/glob semantics.
_RESOLVE_URL_RE = re.compile(
    r"https://huggingface\.co/datasets/defeatbeta/yahoo-finance-data/resolve/[^\s'\"]+\.parquet"
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


def redact_signed_urls(text: str) -> str:
    """Strip URL query strings so logs never persist signed parameters."""
    return _SIGNED_URL_RE.sub(r"\1?<redacted>", text)


def rewrite_resolve_urls(sql: str, resolve) -> str:
    """Replace pinned resolve URLs using `resolve(url)`; keep original on failure.

    Exact file-list syntax avoids cache_httpfs treating signed query strings as
    glob patterns. Non-Parquet URLs are deliberately left unchanged.
    """

    def _resolve_url(resolve_url):
        try:
            return resolve(resolve_url)
        except Exception:
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
        self._hf_client = HuggingFaceClient()
        self._initialize_connection()
        self._validate_httpfs_cache()

    def _initialize_connection(self) -> None:
        started_ns = time.perf_counter_ns()
        status = "ok"
        try:
            self.connection = duckdb.connect(":memory:")
            self.logger.debug("DuckDB connection initialized.")

            duckdb_settings = self.config.get_duckdb_settings()
            if self.http_proxy:
                duckdb_settings.append(f"SET GLOBAL http_proxy = '{self.http_proxy}';")

            if self.log_level and self.log_level == logging.DEBUG:
                duckdb_settings.append("CALL enable_logging('HTTP', level = 'DEBUG', storage = 'stdout')")

            for query in duckdb_settings:
                self.logger.debug(f"DuckDB settings: {query}")
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

    def _validate_httpfs_cache(self):
        """Validate httpfs cache against remote data; clear cache if outdated.

        The remote update_time is fetched via plain HTTP (HuggingFaceClient).
        The locally cached update_time is read directly from the spec.json file
        that cache_httpfs already wrote to disk — bypassing DuckDB entirely.
        This eliminates the cross-process file-lock conflict that occurred when
        multiple processes shared the same cache_httpfs directory.
        """
        spec_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/spec.json"

        started_ns = time.perf_counter_ns()
        status = "ok"
        try:
            remote_update_time = HuggingFaceClient().get_data_update_time()
            cached_update_time = self._read_cached_spec_update_time()

            if cached_update_time == remote_update_time:
                self.logger.info(f"Cache is up-to-date. Update time: {cached_update_time}")
            else:
                self.logger.info(
                    f"Cache outdated. Cached: {cached_update_time}, Remote: {remote_update_time}. "
                    f"Clearing cache..."
                )
                self._clear_cache()
                # Re-download spec.json via DuckDB so the cache file is repopulated
                # and the next startup can read it directly again.
                self.query(f"SELECT * FROM '{spec_url}'")
                self.logger.info(f"Cache refreshed. Update time: {remote_update_time}")

        except Exception as e:
            status = "error"
            self.logger.error(f"Failed to validate httpfs cache: {str(e)}")
            raise
        finally:
            _record_performance(
                "duckdb.validate_httpfs_cache",
                started_ns,
                time.perf_counter_ns(),
                status=status,
            )

    def _read_cached_spec_update_time(self) -> Optional[str]:
        """Read update_time directly from the spec.json file on disk, bypassing DuckDB.

        cache_httpfs names cached files as:
            {url_hash}-{filename}-{start_byte}-{end_byte}
        We scan the cache directory for any file with 'spec.json' in its name
        and parse it as JSON.  Returns None when the file is absent or unreadable
        (e.g. first run, or corrupted by a killed write).
        """
        cache_dir = self.config.get_cache_directory()
        try:
            for filename in os.listdir(cache_dir):
                if 'spec.json' in filename:
                    try:
                        with open(os.path.join(cache_dir, filename), 'r') as f:
                            data = json.loads(f.read())
                        update_time = data.get('update_time')
                        if update_time:
                            self.logger.debug(f"Read cached update_time from {filename}: {update_time}")
                            return update_time
                    except Exception as e:
                        self.logger.debug(f"Could not read cached spec.json ({filename}): {e}")
                        continue
        except OSError:
            pass
        return None

    def _clear_cache(self):
        """Clear httpfs cache via DuckDB API."""
        started_ns = time.perf_counter_ns()
        self.query("SELECT cache_httpfs_clear_cache()")
        _record_performance(
            "duckdb.clear_httpfs_cache",
            started_ns,
            time.perf_counter_ns(),
        )
        self.logger.info("httpfs cache cleared")

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

    def _invalidate_resolved_urls(self, sql: str) -> None:
        resolve_urls = set(_RESOLVE_URL_RE.findall(sql))
        with self._cdn_lock:
            for resolve_url in resolve_urls:
                self._cdn_cache.pop(resolve_url, None)

    @contextmanager
    def _get_cursor(self):
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def _execute_query(self, sql: str) -> pd.DataFrame:
        self.logger.debug(f"Executing query: {redact_signed_urls(sql)}")
        started_ns = time.perf_counter_ns()
        cursor_opened_ns = started_ns
        materialized_ns = started_ns
        ended_ns = started_ns
        status = "error"
        result = None
        try:
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
            events = (
                ("duckdb.cursor.open", started_ns, cursor_opened_ns, {}),
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
