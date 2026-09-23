from defeatbeta_api.utils.util import validate_memory_limit, validate_httpfs_cache_directory


class Configuration:
    """DuckDB/httpfs client settings.

    Attributes are assigned dynamically from __init__ parameters (see
    signature); the annotations below exist so static analysis can resolve
    them. ``resolve_direct`` enables the benchmark-H4 path: resolve pinned HF
    URLs to signed CDN URLs once per TTL while retaining cache_httpfs.
    """

    http_keep_alive: bool
    http_timeout: int
    http_retries: int
    http_retry_backoff: float
    http_retry_wait_ms: int
    memory_limit: str
    threads: int
    parquet_metadata_cache: bool
    cache_httpfs_ignore_sigpipe: bool
    cache_httpfs_type: str
    cache_httpfs_disk_size: int
    cache_httpfs_cache_block_size: int
    cache_httpfs_enable_metadata_cache: bool
    cache_httpfs_metadata_cache_entry_size: int
    cache_httpfs_metadata_cache_entry_timeout_millisec: int
    cache_httpfs_enable_file_handle_cache: bool
    cache_httpfs_file_handle_cache_entry_size: int
    cache_httpfs_file_handle_cache_entry_timeout_millisec: int
    cache_httpfs_max_in_mem_cache_block_count: int
    cache_httpfs_in_mem_cache_block_timeout_millisec: int
    resolve_direct: bool
    resolve_ttl_seconds: int

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
            cache_httpfs_ignore_sigpipe=True,
            cache_httpfs_type='on_disk',
            cache_httpfs_disk_size=1 * 1024 * 1024 * 1024,
            cache_httpfs_cache_block_size=1 * 1024 * 1024,
            cache_httpfs_enable_metadata_cache=True,
            cache_httpfs_metadata_cache_entry_size=1024,
            cache_httpfs_metadata_cache_entry_timeout_millisec=8 * 3600 * 1000,
            cache_httpfs_enable_file_handle_cache=True,
            cache_httpfs_file_handle_cache_entry_size=64,
            cache_httpfs_file_handle_cache_entry_timeout_millisec=8 * 3600 * 1000,
            cache_httpfs_max_in_mem_cache_block_count=64,
            cache_httpfs_in_mem_cache_block_timeout_millisec=1800 * 1000,
            resolve_direct=True,
            resolve_ttl_seconds=1800,
    ):
        configs = locals()
        configs.pop('self')

        for key, value in configs.items():
            setattr(self, key, value)

    def get_duckdb_settings(self):
        base = [
            f"SET GLOBAL http_keep_alive = {self.http_keep_alive}",
            f"SET GLOBAL http_timeout = {self.http_timeout}",
            f"SET GLOBAL http_retries = {self.http_retries}",
            f"SET GLOBAL http_retry_backoff = {self.http_retry_backoff}",
            f"SET GLOBAL http_retry_wait_ms = {self.http_retry_wait_ms}",
            f"SET GLOBAL memory_limit = '{validate_memory_limit(self.memory_limit)}'",
            f"SET GLOBAL threads = {self.threads}",
            f"SET GLOBAL parquet_metadata_cache = {self.parquet_metadata_cache}",
        ]
        return [
            "INSTALL cache_httpfs FROM community",
            "LOAD cache_httpfs",
            # Signed CDN URLs embed a literal '*' in content-disposition.
            # read_parquet receives an exact file list so '?' is not a glob.
            "SET GLOBAL allow_asterisks_in_http_paths = true",
            *base,
            f"SET GLOBAL cache_httpfs_ignore_sigpipe={self.cache_httpfs_ignore_sigpipe}",
            f"SET GLOBAL cache_httpfs_type='{self.cache_httpfs_type}'",
            f"SET GLOBAL cache_httpfs_cache_directory='{validate_httpfs_cache_directory()}'",
            f"SET GLOBAL cache_httpfs_min_disk_bytes_for_cache={self.cache_httpfs_disk_size}",
            f"SET GLOBAL cache_httpfs_cache_block_size={self.cache_httpfs_cache_block_size}",
            f"SET GLOBAL cache_httpfs_profile_type='temp'",
            f"SET GLOBAL cache_httpfs_enable_metadata_cache={self.cache_httpfs_enable_metadata_cache}",
            f"SET GLOBAL cache_httpfs_metadata_cache_entry_size={self.cache_httpfs_metadata_cache_entry_size}",
            f"SET GLOBAL cache_httpfs_metadata_cache_entry_timeout_millisec={self.cache_httpfs_metadata_cache_entry_timeout_millisec}",
            f"SET GLOBAL cache_httpfs_enable_file_handle_cache={self.cache_httpfs_enable_file_handle_cache}",
            f"SET GLOBAL cache_httpfs_file_handle_cache_entry_size={self.cache_httpfs_file_handle_cache_entry_size}",
            f"SET GLOBAL cache_httpfs_file_handle_cache_entry_timeout_millisec={self.cache_httpfs_file_handle_cache_entry_timeout_millisec}",
            f"SET GLOBAL cache_httpfs_max_in_mem_cache_block_count={self.cache_httpfs_max_in_mem_cache_block_count}",
            f"SET GLOBAL cache_httpfs_in_mem_cache_block_timeout_millisec={self.cache_httpfs_in_mem_cache_block_timeout_millisec}"
        ]
