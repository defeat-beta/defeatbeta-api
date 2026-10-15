"""Use the actual product with isolated query caches and explicit preparation."""

from contextlib import contextmanager
import importlib
import logging
from pathlib import Path
import shutil
from threading import Lock
from unittest.mock import patch

import psutil

from benchmark.e2e import plan


class ProductBackend:
    def __init__(self, directory, workload=None):
        from defeatbeta_api.client.duckdb_conf import Configuration
        from defeatbeta_api.data.ticker import Ticker

        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.workload = workload
        self._configuration = Configuration
        self._ticker = Ticker
        self._tickers = {}
        self.cache_directory = self.directory / "active-cache"
        self.memory_capacity = min(512 * 1024**2, psutil.virtual_memory().total // 16)
        self.initial_free_bytes = shutil.disk_usage(self.directory).free
        self._config = None

    def close(self):
        from defeatbeta_api.client import duckdb_client

        with duckdb_client._lock:
            clients = list(duckdb_client._instances.values())
            duckdb_client._instances.clear()
        for client in clients:
            client.close()
        self._tickers.clear()

    def reset(self):
        self.close()
        try:
            shared = importlib.import_module("defeatbeta_api.client.shared_resources")
        except ModuleNotFoundError:
            shared = None
        if shared is not None:
            for name in ("FOOTERS", "PARQUET_INDEXES", "FILE_SIZES", "RESOLVED_URLS", "DATASET_SPECS"):
                getattr(shared, name).clear()
        if self.cache_directory.exists():
            shutil.rmtree(self.cache_directory)
        self.cache_directory.mkdir()
        if shutil.disk_usage(self.directory).free < 512 * 1024**2:
            raise RuntimeError("Insufficient disk space to prepare a valid cache scenario")
        self._config = self._configuration(
            cache_directory=str(self.cache_directory),
            cache_data_disk_limit_bytes=(self.workload or {}).get("cache_capacity_bytes", 2**60),
            cache_data_memory_limit_bytes=self.memory_capacity)

    def ticker(self, symbol):
        if self._config is None:
            self.reset()
        if symbol not in self._tickers:
            self._tickers[symbol] = self._ticker(symbol, config=self._config, log_level=logging.WARNING)
        return self._tickers[symbol]

    @property
    def client(self):
        return next(iter(self._tickers.values())).duckdb_client

    def drain(self):
        clients = {id(ticker.duckdb_client): ticker.duckdb_client for ticker in self._tickers.values()}
        errors = 0
        for client in clients.values():
            filesystem = getattr(client, "_dataset_fs", None)
            if filesystem is not None:
                errors += filesystem.await_pending()["errors"]
        if errors:
            raise RuntimeError(f"Prefetch did not finish successfully: {errors} errors")
        return {"errors": 0}

    @contextmanager
    def probe(self):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

        original = DatasetCacheFileSystem._request_range
        state, lock = {"misses": 0}, Lock()

        def request_range(filesystem, *args, **kwargs):
            with lock:
                state["misses"] += 1
            return original(filesystem, *args, **kwargs)

        with patch.object(DatasetCacheFileSystem, "_request_range", request_range):
            yield state

    def settings(self):
        return {"disk_limit_bytes": (self.workload or {}).get("cache_capacity_bytes", 2**60),
                "memory_limit_bytes": self.memory_capacity,
                "free_disk_bytes_at_start": self.initial_free_bytes,
                "disk_policy": "No budget eviction; physical capacity and measured misses remain validity checks",
                "native_file_cache": self.client.connection.execute(
                    "SELECT current_setting('enable_external_file_cache')").fetchone()[0]}


def discover(backend):
    """Freeze parameters outside timing using public data retrieval calls."""
    from defeatbeta_api.data.company_meta import CompanyMeta
    from defeatbeta_api.data.ticker import Ticker

    backend.reset()
    companies = CompanyMeta(config=backend._config, log_level=logging.WARNING).get_all_companies_info()
    selected = plan.select_sample(companies)
    bodies, observations = {}, {}
    for company in selected:
        symbol = company.get("symbol", company.get("ticker"))
        ticker = backend.ticker(symbol)
        transcripts = ticker.earning_call_transcripts().get_transcripts_list()
        news = ticker.news().get_news_list()
        bodies[symbol] = {}
        if not transcripts.empty:
            row = transcripts.sort_values(["fiscal_year", "fiscal_quarter"]).iloc[-1]
            bodies[symbol]["transcript_body"] = {
                "fiscal_year": int(row["fiscal_year"]), "fiscal_quarter": int(row["fiscal_quarter"])}
        if not news.empty:
            row = news.sort_values(["report_date", "uuid"]).iloc[-1]
            bodies[symbol]["news_body"] = {"uuid": str(row["uuid"])}
        prices = ticker.price()
        observations[symbol] = {"financial_currency": company.get("financial_currency"),
                                "price_rows": len(prices), "transcript_rows": len(transcripts),
                                "news_rows": len(news)}
    backend.drain()
    dataset = {"update_time": backend.client._data_update_time,
               "footer_index": backend.client._footer_index}
    workload = plan.build_plan(selected, plan.query_methods(Ticker), bodies=bodies, dataset=dataset)
    workload["sample_observations"] = observations
    workload["catalog_ticker_count"] = len(companies)
    workload["sample_policy"] = (
        "Maintainer-approved fixed sample of eight well-known issuers; "
        "query availability checked before timing; no automatic replacement"
    )
    workload["sha256"] = plan.checksum({key: value for key, value in workload.items() if key != "sha256"})
    return workload
