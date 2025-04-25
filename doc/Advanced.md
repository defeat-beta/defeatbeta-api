from defeatbeta_api.client.duckdb_conf import Configuration

# Advanced Usage

## Set Http Proxy

```python
import defeatbeta_api
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210")
```

## Set Logging

```python
import defeatbeta_api
import logging
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", log_level=logging.DEBUG)
```

## Set Configuration

```python
import defeatbeta_api
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", config=Configuration())
```

| name                                                  | description                                                                                                                                                                                                                                                                                                                   |     default      |
|:------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------:|
| http_keep_alive                                       | Keep alive connections. Setting this to false can help when running into connection failures                                                                                                                                                                                                                                  |       True       |
| http_timeout                                          | HTTP timeout read/write/connection/retry (in seconds)	                                                                                                                                                                                                                                                                        |       120        |
| http_retries                                          | HTTP retries on I/O error	                                                                                                                                                                                                                                                                                                    |        5         |
| http_retry_backoff                                    | Backoff factor for exponentially increasing retry wait time		                                                                                                                                                                                                                                                                 |       2.0        |
| http_retry_wait_ms                                    | Time between retries			                                                                                                                                                                                                                                                                                                       |       1000       |
| memory_limit                                          | The memory_limit parameter supports specifying either a fixed memory value (e.g., 10GB) or a percentage of system memory (e.g., 50%), automatically converting it into a valid unit.                                                                                                                                          |      '80%'       |
| threads                                               | The number of total threads used by the system.				                                                                                                                                                                                                                                                                           |        4         |
| parquet_metadata_cache                                | Cache Parquet metadata - useful when reading the same files multiple times					                                                                                                                                                                                                                                               |       True       |
| cache_httpfs_ignore_sigpipe                           | Whether to ignore SIGPIPE for the extension. By default not ignored. Once ignored, it cannot be reverted.					                                                                                                                                                                                                                |       True       |
| cache_httpfs_type                                     | Type for cached filesystem. Currently there're two types available, one is in_mem, another is on_disk. By default we use on-disk cache. Set to noop to disable, which behaves exactly same as httpfs extension.						                                                                                                         |    'on_disk'     |
| cache_httpfs_directory_name                           | The parameter defines the HTTPFS cache subdirectory, automatically created in the system's temp folder with versioning (e.g., /tmp/{cache_httpfs_directory_name}/{version}/).                                                                                                                                                 |  'defeat_cache'  |
| cache_httpfs_disk_size                                | Min number of bytes on disk for the cache filesystem to enable on-disk cache; if left bytes is less than the threshold, LRU based cache file eviction will be performed.By default, 5% disk space will be reserved for other usage. When min disk bytes specified with a positive value, the default value will be overriden. | 1*1024*1024*1024 |
| cache_httpfs_cache_block_size                         | Block size for cache, applies to both in-memory cache filesystem and on-disk cache filesystem. It's worth noting for on-disk filesystem, all existing cache files are invalidated after config update.	                                                                                                                       |   1*1024*1024    |
| cache_httpfs_enable_metadata_cache                    | Whether metadata cache is enable for cache filesystem. By default enabled.		                                                                                                                                                                                                                                                  |       True       |
| cache_httpfs_metadata_cache_entry_size                | Max cache size for metadata LRU cache.			                                                                                                                                                                                                                                                                                     |       1024       |
| cache_httpfs_metadata_cache_entry_timeout_millisec    | Cache entry timeout in milliseconds for metadata LRU cache.				                                                                                                                                                                                                                                                               |   8*3600*1000    |
| cache_httpfs_enable_file_handle_cache                 | Whether file handle cache is enable for cache filesystem. By default enabled.					                                                                                                                                                                                                                                            |       True       |
| cache_httpfs_file_handle_cache_entry_size             | Max cache size for file handle cache.						                                                                                                                                                                                                                                                                                   |       1024       |
| cache_httpfs_file_handle_cache_entry_timeout_millisec | Cache entry timeout in milliseconds for file handle cache.							                                                                                                                                                                                                                                                             |   8*3600*1000    |
| cache_httpfs_max_in_mem_cache_block_count             | Max in-memory cache block count for in-memory caches for all cache filesystems, so users are able to configure the maximum memory consumption. It's worth noting it should be set only once before all filesystem access, otherwise there's no affect.								                                                                |        64        |
| cache_httpfs_max_in_mem_cache_block_count             | Data block cache entry timeout in milliseconds.									                                                                                                                                                                                                                                                                      |    1800*1000     |
