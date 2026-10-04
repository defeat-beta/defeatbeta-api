from pathlib import Path
from typing import Optional

from defeatbeta_api.utils.util import validate_cache_directory, validate_memory_limit


class Configuration:
    """DuckDB settings and DefeatBeta's demand-driven dataset cache limits."""

    def __init__(
            self,
            http_keep_alive=True,
            http_timeout=120,
            http_retries=5,
            http_retry_backoff=2.0,
            http_retry_wait_ms=1000,
            memory_limit='80%',
            threads=4,
            parquet_metadata_cache=True,
            resolve_direct=True,
            resolve_ttl_seconds=1800,
            cache_enabled=True,
            cache_directory: Optional[str] = None,
            cache_max_disk_bytes=5 * 1024 * 1024 * 1024,
            cache_max_memory_bytes=64 * 1024 * 1024,
            cache_workers=3,
            cache_version_check_seconds=300,
            cache_network_connections=1,
            cache_network_chunk_size=0,
            cache_footer_preload=True,
            cache_column_prefetch=True,
    ):
        if cache_version_check_seconds < 0:
            raise ValueError("Cache version check interval must not be negative")
        if cache_network_connections < 1 or cache_network_chunk_size < 0:
            raise ValueError("Cache network connections and chunk size are invalid")
        configs = locals()
        configs.pop('self')

        for key, value in configs.items():
            setattr(self, key, value)

    def get_cache_directory(self) -> str:
        if self.cache_directory is None:
            return validate_cache_directory()
        directory = Path(self.cache_directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory)

    def get_duckdb_settings(self):
        return [
            "INSTALL httpfs",
            "LOAD httpfs",
            # Signed CDN URLs may contain literal asterisks in query parameters.
            "SET GLOBAL allow_asterisks_in_http_paths = true",
            f"SET GLOBAL http_keep_alive = {self.http_keep_alive}",
            f"SET GLOBAL http_timeout = {self.http_timeout}",
            f"SET GLOBAL http_retries = {self.http_retries}",
            f"SET GLOBAL http_retry_backoff = {self.http_retry_backoff}",
            f"SET GLOBAL http_retry_wait_ms = {self.http_retry_wait_ms}",
            f"SET GLOBAL memory_limit = '{validate_memory_limit(self.memory_limit)}'",
            f"SET GLOBAL threads = {self.threads}",
            f"SET GLOBAL parquet_metadata_cache = {self.parquet_metadata_cache}",
        ]
