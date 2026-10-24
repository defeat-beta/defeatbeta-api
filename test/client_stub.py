"""Construct DuckDB clients for unit tests without a connection or network access."""

import logging
from threading import Lock

from defeatbeta_api.client.duckdb_client import Configuration, DuckDBClient
from defeatbeta_api.client.shared_resources import SharedCache


def bare_client(**attributes):
    """Return a client with the attributes __init__ sets, overridden by the caller."""
    client = DuckDBClient.__new__(DuckDBClient)
    values = {
        "connection": None, "http_proxy": None, "config": Configuration(),
        "log_level": logging.INFO, "logger": logging.getLogger("test-duckdb-client"),
        "_resolve_ttl": 1800, "_cdn_lock": Lock(), "_dataset_cdn_cache": {},
        "_hf_client": None, "_dataset_fs": None, "_uncached_fs": None,
        "_network_fs_lock": Lock(), "_parquet_indexes": {}, "_parquet_index_locks": {},
        "_parquet_index_locks_guard": Lock(), "_prepared_footers": set(),
        "_data_update_time": None, "_footer_index": {}, "_version_lock": Lock(),
        "_dataset_generation": 0, "_catalog_cache": SharedCache(), "_last_version_check": 0.0,
    }
    values.update(attributes)
    for name, value in values.items():
        setattr(client, name, value)
    return client
