"""Exercise real query caches through a fixed-data service without timing claims."""

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark.support.adapter import dataset_endpoint
from benchmark.e2e.backend import ProductBackend
from benchmark.e2e import execution, plan
from benchmark.support.fixture import generate
from benchmark.support.server import serve_fixture
from benchmark import common


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for cache integration")
class TestE2ECacheIntegration(unittest.TestCase):
    def test_cold_queries_are_isolated_and_complete_warm_work_hits_local_cache(self):
        from defeatbeta_api.client.shared_resources import close_network_resources

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}, {"ticker": "BABA"}],
                {"price": {"call": "price", "kwargs": {}}, "info": {"call": "info", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server, \
                    dataset_endpoint(server["url"]), redirect_stdout(io.StringIO()), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": server["certificate"],
                                           "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}):
                backend = ProductBackend(directory / "cache", workload)
                try:
                    cold = execution.measure_latency(workload, backend, "cold")
                    self.assertEqual(cold["status"], "complete", cold)
                    self.assertTrue(all(row["cache_misses"] > 0 for row in cold["results"]))
                    cached = execution.measure_latency(workload, backend, "cached")
                    self.assertEqual(cached["status"], "complete", cached)
                    self.assertEqual(cached["cache_misses"], 0)
                    for concurrency in (1, 4, 16, 64, 128):
                        batch = execution.measure_throughput(workload, backend, "cached", concurrency)
                        self.assertEqual(batch["status"], "complete", batch)
                        self.assertEqual(batch["cache_misses"], 0)
                        self.assertEqual({row["id"] for row in batch["results"]},
                                         {task["id"] for task in plan.tasks(workload)})
                finally:
                    backend.close()
                    close_network_resources()

    def test_disposable_worker_materializes_real_calls_with_recorded_identity(self):
        from benchmark.worker import run
        from defeatbeta_api.client.shared_resources import close_network_resources

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}],
                                      {"price": {"call": "price", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server, \
                    redirect_stdout(io.StringIO()), patch.dict(os.environ, {
                        "SSL_CERT_FILE": server["certificate"], "NO_PROXY": "localhost,127.0.0.1",
                        "no_proxy": "localhost,127.0.0.1"}):
                try:
                    result = run({"source": str(common.ROOT), "source_hashes": common.source_hashes(),
                                  "dependencies": common.environment_info()["dependencies"],
                                  "endpoint": server["url"], "action": "measure", "plan": workload,
                                  "cache_directory": str(directory / "cache"), "phase": {
                                      "kind": "latency", "state": "cached", "concurrency": 1}})
                finally:
                    close_network_resources()
            self.assertEqual(result["status"], "complete", result)
            self.assertEqual(result["cache_misses"], 0)
            self.assertEqual(result["results"][0]["fingerprint"]["rows"], 32768)
            self.assertTrue(result["observed_dataset"]["footer_index"])
            self.assertIn("dcf_data", result["api_coverage"])
