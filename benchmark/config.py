"""Pinned stock-price workload and the current client's baseline settings."""

import re

DATASET = "defeatbeta/yahoo-finance-data"
DEFAULT_REVISION = "a46d68650c1f90b7331608350dced8364047b3f7"
# Candidate row groups 0, 184, and 367 in DEFAULT_REVISION (368 groups total).
DEFAULT_SYMBOLS = ("AAPL", "KDP", "ZTS")
DEFAULT_RUNS = 3
DEFAULT_TIMEOUT = 600.0

# Match Configuration defaults; resolve its memory percentage in the runner.
BASELINE_SETTINGS = {
    "http_keep_alive": False,
    "http_timeout": 120,
    "http_retries": 5,
    "http_retry_backoff": 2.0,
    "http_retry_wait_ms": 1000,
    "threads": 4,
    "parquet_metadata_cache": True,
    "cache_httpfs_ignore_sigpipe": True,
    "cache_httpfs_type": "on_disk",
    "cache_httpfs_min_disk_bytes_for_cache": 1024 ** 3,
    "cache_httpfs_cache_block_size": 1024 ** 2,
    "cache_httpfs_profile_type": "temp",
    "cache_httpfs_enable_metadata_cache": True,
    "cache_httpfs_metadata_cache_entry_size": 1024,
    "cache_httpfs_metadata_cache_entry_timeout_millisec": 8 * 3600 * 1000,
    "cache_httpfs_enable_file_handle_cache": True,
    "cache_httpfs_file_handle_cache_entry_size": 64,
    "cache_httpfs_file_handle_cache_entry_timeout_millisec": 8 * 3600 * 1000,
    "cache_httpfs_max_in_mem_cache_block_count": 64,
    "cache_httpfs_in_mem_cache_block_timeout_millisec": 1800 * 1000,
}


def validate_symbol(symbol):
    if not symbol or not symbol.strip() or any(ord(c) < 32 for c in symbol):
        raise ValueError("symbol must be nonempty and contain no control characters")
    return symbol


def stock_prices_url(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full, immutable Hugging Face commit SHA")
    return f"https://huggingface.co/datasets/{DATASET}/resolve/{revision}/data/US/stock_prices.parquet"
