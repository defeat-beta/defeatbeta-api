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

## Set Configuration

```python
import defeatbeta_api
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("BABA", config=Configuration())
```

| name                                                  | description                                                                                                                                                                                                                                                                                                                   |    default     |
|:------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------:|
| http_keep_alive                                       | Keep alive connections. Setting this to false can help when running into connection failures                                                                                                                                                                                                                                  |      True      |
| http_timeout                                          | HTTP timeout read/write/connection/retry (in seconds)                                                                                                                                                                                                                                                                         |      120       |
| http_retries                                          | HTTP retries on I/O error                                                                                                                                                                                                                                                                                                     |       5        |
| http_retry_backoff                                    | Backoff factor for exponentially increasing retry wait time                                                                                                                                                                                                                                                                   |      2.0       |
| http_retry_wait_ms                                    | Time between retries                                                                                                                                                                                                                                                                                                          |      1000      |
| memory_limit                                          | The memory_limit parameter supports specifying either a fixed memory value (e.g., 10GB) or a percentage of system memory (e.g., 50%), automatically converting it into a valid unit.                                                                                                                                          |     '80%'      |
| threads                                               | The number of total threads used by the system.                                                                                                                                                                                                                                                                               |       4        |
| parquet_metadata_cache                                | Cache Parquet metadata - useful when reading the same files multiple times                                                                                                                                                                                                                                                    |      True      |
| cache_enabled | Enable the project's on-demand local cache for pinned Parquet and JSON files. Set to false for uncached standard HTTP reads. | True |
| cache_directory | Cache root. Defaults to `/tmp/defeatbeta/dataset-cache/{version}/` on macOS/Linux and `<tempdir>/defeatbeta/dataset-cache/{version}/` on Windows. Legacy extension files are not reused or deleted. | None |
| cache_block_size | Downloaded range block size in bytes. | 1048576 |
| cache_max_disk_bytes | Maximum retained block bytes; older blocks are evicted as needed. | 1073741824 |
| cache_max_memory_blocks | Maximum recently used blocks kept in memory. Zero disables the memory tier. | 64 |
| cache_workers | Maximum concurrent Range GET workers and HTTP connections. | 3 |
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
