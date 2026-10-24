"""Use the actual product with isolated query caches and explicit preparation."""

from contextlib import contextmanager
import importlib
import inspect
import logging
from pathlib import Path
import shutil

import psutil

from benchmark.e2e import plan
from benchmark.e2e.probe import observe_ranges


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

    def reset(self, *, preserve_disk=False):
        self.close()
        try:
            shared = importlib.import_module("defeatbeta_api.client.shared_resources")
        except ModuleNotFoundError:
            shared = None
        if shared is not None:
            for name in ("FOOTERS", "PARQUET_INDEXES", "FILE_SIZES", "RESOLVED_URLS", "DATASET_SPECS"):
                getattr(shared, name).clear()
        if preserve_disk:
            if not self.cache_directory.is_dir():
                raise ValueError("Disk reuse requires an existing disk cache from the first round")
        else:
            if self.cache_directory.exists():
                shutil.rmtree(self.cache_directory)
            self.cache_directory.mkdir()
        if shutil.disk_usage(self.directory).free < 512 * 1024**2:
            raise RuntimeError("Insufficient disk space to prepare a valid cache scenario")
        options = {"cache_directory": str(self.cache_directory),
                   "cache_data_memory_limit_bytes": self.memory_capacity}
        default_disk_limit = inspect.signature(self._configuration).parameters[
            "cache_data_disk_limit_bytes"].default
        if default_disk_limit is not None:
            # Only versions that evict by disk size need the generous limit.
            options["cache_data_disk_limit_bytes"] = (self.workload or {}).get("cache_capacity_bytes", 2**60)
        self._config = self._configuration(**options)

    def dataset(self):
        if not self._tickers:
            return {}
        return {"update_time": self.client._data_update_time,
                "footer_index": self.client._footer_index}

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
        # Shared clients and filesystems must contribute their counters only once.
        def filesystems():
            return {id(fs): fs for ticker in self._tickers.values()
                    if (fs := getattr(ticker.duckdb_client, "_dataset_fs", None)) is not None}

        initial = filesystems()
        before = {key: fs.metrics() for key, fs in initial.items()}
        with observe_ranges() as evidence:
            try:
                yield evidence
            finally:
                totals = {"cache_hits": 0, "cache_misses": 0, "downloaded_bytes": 0,
                          "range_requests": 0, "range_seconds": 0.0}
                for key, fs in {**initial, **filesystems()}.items():
                    for metric, value in fs.metrics().items():
                        totals[metric] += value - before.get(key, {}).get(metric, 0)
                if any(value < 0 for value in totals.values()):
                    raise ValueError("Product cache counters reset during measurement")
                evidence["metrics"] = totals

    def settings(self):
        return {"disk_limit_bytes": (self.workload or {}).get("cache_capacity_bytes", 2**60),
                "memory_limit_bytes": self.memory_capacity,
                "free_disk_bytes_at_start": self.initial_free_bytes,
                "disk_policy": "No budget eviction; physical capacity and measured misses remain validity checks",
                "native_file_cache": self.client.connection.execute(
                    "SELECT current_setting('enable_external_file_cache')").fetchone()[0] if self._tickers else None}


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
