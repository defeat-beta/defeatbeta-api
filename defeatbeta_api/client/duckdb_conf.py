from defeatbeta_api.utils.util import validate_memory_limit, validate_httpfs_cache_directory


class Configuration:
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
            cache_httpfs_directory_name='defeat_cache',
            cache_httpfs_disk_size=1 * 1024 * 1024 * 1024,
            cache_httpfs_cache_block_size=1 * 1024 * 1024,
            cache_httpfs_enable_metadata_cache=True,
            cache_httpfs_metadata_cache_entry_size=1024,
            cache_httpfs_metadata_cache_entry_timeout_millisec=8 * 3600 * 1000,
            cache_httpfs_enable_file_handle_cache=True,
            cache_httpfs_file_handle_cache_entry_size=1024,
            cache_httpfs_file_handle_cache_entry_timeout_millisec=8 * 3600 * 1000,
            cache_httpfs_max_in_mem_cache_block_count=64,
            cache_httpfs_in_mem_cache_block_timeout_millisec=1800 * 1000,
    ):
        configs = locals()
        configs.pop('self')

        for key, value in configs.items():
            setattr(self, key, value)

    def get_duckdb_settings(self):
        return [
            "INSTALL cache_httpfs FROM community",
            "LOAD cache_httpfs",
            f"SET GLOBAL http_keep_alive = {self.http_keep_alive}",
            f"SET GLOBAL http_timeout = {self.http_timeout}",
            f"SET GLOBAL http_retries = {self.http_retries}",
            f"SET GLOBAL http_retry_backoff = {self.http_retry_backoff}",
            f"SET GLOBAL http_retry_wait_ms = {self.http_retry_wait_ms}",
            f"SET GLOBAL memory_limit = '{validate_memory_limit(self.memory_limit)}'",
            f"SET GLOBAL threads = {self.threads}",
            f"SET GLOBAL parquet_metadata_cache = {self.parquet_metadata_cache}",
            f"SET GLOBAL cache_httpfs_ignore_sigpipe={self.cache_httpfs_ignore_sigpipe}",
            f"SET GLOBAL cache_httpfs_type='{self.cache_httpfs_type}'",
            f"SET GLOBAL cache_httpfs_cache_directory='{validate_httpfs_cache_directory(self.cache_httpfs_directory_name)}'",
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
