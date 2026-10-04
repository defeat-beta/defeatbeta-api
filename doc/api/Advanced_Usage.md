<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Advanced Usage](#advanced-usage)
  - [Use SQL to Access Data](#use-sql-to-access-data)
  - [Set Http Proxy (if you’re in a region where cannot access Hugging Face)](#set-http-proxy-if-youre-in-a-region-where-cannot-access-hugging-face)
  - [Set Logging](#set-logging)
  - [Set Configuration](#set-configuration)
  - [Load from Hugging Face](#load-from-hugging-face)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Advanced Usage

## Use SQL to Access Data

SQL syntax reference: [DuckDB.org](https://duckdb.org/)

```python
import defeatbeta_api
import logging
from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.duckdb_client import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.utils.const import stock_profile

duckdb_client = DuckDBClient(log_level=logging.DEBUG, config=Configuration(threads=8))
huggingface_client = HuggingFaceClient()
url = huggingface_client.get_url_path(stock_profile)
sql = f"SELECT * FROM '{url}' WHERE symbol = 'TSLA'"
result = duckdb_client.query(sql)
print(result)
```

## Set Http Proxy (if you’re in a region where cannot access Hugging Face)

```python
import defeatbeta_api
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", http_proxy="http://127.0.0.1:8118")
```

## Set Logging

```python
import defeatbeta_api
import logging
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", log_level=logging.DEBUG)
```

DefeatBeta writes its own diagnostics to standard output without changing the
application's root Python logger. Pytest captures output from passing tests by
default; use `pytest -s` or `pytest --capture=tee-sys` to see these messages
while running a test in a terminal or IDE.

## Set Configuration

```python
import defeatbeta_api
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", config=Configuration())
```

| name                                                  | description                                                                                                                                                                                                                                                                                                                   |    default     |
|:------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------:|
| http_keep_alive                                       | Keep-alive for DuckDB's standard HTTP reader; does not control the project cache's HTTP pool.                                                                                                                                                                                                                                 |      True      |
| http_timeout                                          | HTTP timeout in seconds for DuckDB's standard HTTP reader and the project cache transport.                                                                                                                                                                                                                                    |      120       |
| http_retries                                          | I/O retry count for DuckDB's standard HTTP reader, not the project cache transport.                                                                                                                                                                                                                                           |       5        |
| http_retry_backoff                                    | Exponential retry backoff for DuckDB's standard HTTP reader, not the project cache transport.                                                                                                                                                                                                                                  |      2.0       |
| http_retry_wait_ms                                    | Retry wait time in milliseconds for DuckDB's standard HTTP reader, not the project cache transport.                                                                                                                                                                                                                            |      1000      |
| memory_limit                                          | The memory_limit parameter supports specifying either a fixed memory value (e.g., 10GB) or a percentage of system memory (e.g., 50%), automatically converting it into a valid unit.                                                                                                                                          |     '80%'      |
| threads                                               | The number of total threads used by the system.                                                                                                                                                                                                                                                                               |       4        |
| parquet_metadata_cache                                | Cache Parquet metadata - useful when reading the same files multiple times                                                                                                                                                                                                                                                    |      True      |
| cache_enabled | Enable the project's on-demand local cache for pinned Parquet and JSON files. Set to false for uncached standard HTTP reads. | True |
| cache_directory | Cache root. Defaults to `/tmp/defeatbeta/dataset-cache/{version}/` on macOS/Linux and `<tempdir>/defeatbeta/dataset-cache/{version}/` on Windows. Cache files are flat. Cache-owned files from older dataset versions are removed after an update is detected; legacy `cache_httpfs` files in the separate `cache/` root are untouched. | None |
| cache_footer_preload | Prepare and persist a Parquet file's footer when that file is first queried. With column prefetch enabled, a simple symbol query also builds an in-memory row-group index from that footer. No footers are fetched during client initialization. | True |
| cache_column_prefetch | Schedule the selected Parquet column chunks ahead of a simple symbol scan. Disabling it leaves DuckDB demand reads and footer preparation intact; primarily useful for A/B diagnostics. | True |
| cache_max_disk_bytes | Maximum retained data-range bytes; older ranges are evicted as needed. Versioned footer extents are retained separately. The 5 GiB default does not trigger a full download. | 5368709120 |
| cache_max_memory_bytes | Maximum data-range bytes retained in memory. Zero disables the data-range memory tier. At most 64 ranges are retained regardless of this budget. | 67108864 |
| cache_workers | Maximum concurrent range-fetch tasks; with one cache network client, also bounds that client's connections. | 3 |
| cache_network_connections | Number of cache HTTP clients per origin. Connections are reused across files on the same origin; idle or closed connections reopen on demand. | 1 |
| cache_network_chunk_size | Split a missing range into parallel network requests of at most this many bytes. Zero disables splitting. | 0 |
| cache_version_check_seconds | Minimum time between remote dataset-version checks for a running client. Set to zero to check before every cached query. | 300 |
| resolve_direct | Resolve pinned Parquet URLs to CDN URLs for the uncached fallback reader. | True |
| resolve_ttl_seconds | Lifetime of the in-process CDN resolution cache, in seconds. | 1800 |


## Load from Hugging Face

This feature requires additional packages that are not installed by default. Install them first:

```bash
pip install datasets huggingface_hub pyarrow
```

> **Note:** If you have a SOCKS proxy configured in your environment (e.g. `ALL_PROXY=socks5://...`), you may encounter the following error:
> ```
> ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
> ```
> Fix it by installing `httpx` with SOCKS support:
> ```bash
> pip install "httpx[socks]"
> ```

Load a dataset and inspect available splits:

```python
from datasets import load_dataset
import datasets

datasets.utils.logging.set_verbosity_debug()

dataset = load_dataset(
    "defeatbeta/yahoo-finance-data",
    data_files="data/stock_prices.parquet"
)

# Inspect available splits
print(dataset)

# Access the 'train' split (or whichever split is available)
ds = dataset["train"]

# Split train and test 80% / 20%
split_datasets = ds.train_test_split(test_size=0.2, seed=0xDEADBEAF)
print(split_datasets)
```
