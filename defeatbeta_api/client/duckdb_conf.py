from defeatbeta_api.utils.util import validate_memory_limit

class Configuration:
    def __init__(
            self,
            http_keep_alive=False,
            http_timeout=120,
            http_retries=5,
            http_retry_backoff=2.0,
            http_retry_wait_ms=1000,
            memory_limit='80%',
            threads=4,
            parquet_metadata_cache=True,
            cache_directory_name="defeat_cache",
    ):
        configs = locals()
        configs.pop('self')

        for key, value in configs.items():
            setattr(self, key, value)

    def get_duckdb_settings(self):
        return [
            f"SET GLOBAL http_keep_alive = {self.http_keep_alive}",
            f"SET GLOBAL http_timeout = {self.http_timeout}",
            f"SET GLOBAL http_retries = {self.http_retries}",
            f"SET GLOBAL http_retry_backoff = {self.http_retry_backoff}",
            f"SET GLOBAL http_retry_wait_ms = {self.http_retry_wait_ms}",
            f"SET GLOBAL memory_limit = '{validate_memory_limit(self.memory_limit)}'",
            f"SET GLOBAL threads = {self.threads}",
            f"SET GLOBAL parquet_metadata_cache = {self.parquet_metadata_cache}",
        ]
