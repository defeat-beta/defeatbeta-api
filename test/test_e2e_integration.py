"""Exercise real query caches through a fixed-data service without timing claims."""

from contextlib import redirect_stdout
import io
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark.support.adapter import dataset_endpoint
from benchmark.e2e.backend import ProductBackend
from benchmark.e2e import execution, plan
from benchmark.support.fixture import generate
from benchmark.support.server import serve_fixture
from benchmark import common


class TestWorkerFailures(unittest.TestCase):
    def test_initialization_errors_keep_the_original_task_ledger(self):
        from benchmark.worker import run

        workload = plan.build_plan([{"ticker": "PDD"}], {"price": {"call": "price", "kwargs": {}}})
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(ProductBackend, "ticker", side_effect=RuntimeError("Expected initialization failure")):
            result = run({"source": str(common.ROOT), "source_hashes": common.source_hashes(),
                          "dependencies": common.environment_info()["dependencies"], "action": "measure",
                          "plan": workload, "cache_directory": temporary,
                          "phase": {"kind": "latency", "state": "cold", "concurrency": 1}})
        self.assertEqual(result["status"], "query_errors")
        self.assertEqual(result["results"][0]["stage"], "initialization")
        self.assertEqual(result["results"][0]["error"], "Expected initialization failure")


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for cache integration")
class TestE2ECacheIntegration(unittest.TestCase):
    def test_new_read_ranges_are_prepared_before_real_cache_measurement(self):
        from defeatbeta_api.client.shared_resources import close_network_resources
        from defeatbeta_api.utils.const import stock_news

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}],
                                      {"price": {"call": "price", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server, \
                    dataset_endpoint(server["url"]), redirect_stdout(io.StringIO()), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": server["certificate"],
                        "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}):
                backend = ProductBackend(directory / "cache", workload)
                original_ticker = backend.ticker
                observed = []

                def ticker(symbol):
                    product = original_ticker(symbol)
                    filesystem = product.duckdb_client._dataset_fs
                    path = filesystem.register(product.huggingface_client.get_url_path(stock_news))

                    class ChangingReadFootprint:
                        calls = 0

                        def price(self):
                            self.calls += 1
                            start = 2048 if self.calls >= 3 else 8
                            filesystem.cat_file(path, start=start, end=start + 32)
                            return {"value": 1}

                    instance = ChangingReadFootprint()
                    observed.append(instance)
                    return instance

                try:
                    with patch.object(backend, "ticker", ticker):
                        latency = execution.measure_latency(workload, backend, "cached")
                        batch = execution.measure_throughput(workload, backend, "cached", 4)
                        with backend.probe() as probe:
                            observed[-1].price()
                            backend.drain()
                        self.assertEqual(probe["misses"], 0)
                    self.assertEqual(latency["status"], "complete", latency)
                    self.assertEqual(batch["status"], "complete", batch)
                    preparations = [latency["results"][0]["cache_preparation"], batch["cache_preparation"]]
                    for preparation in preparations:
                        self.assertEqual([p["cache_misses"] for p in preparation["passes"]], [0])
                    self.assertEqual([instance.calls for instance in observed], [2, 3])
                    self.assertEqual(latency["cache_misses"], 0)
                    self.assertEqual(batch["cache_misses"], 0)
                finally:
                    backend.close()
                    close_network_resources()

    @unittest.skipUnless(os.environ.get("DEFEATBETA_BENCHMARK_BASELINE_PYTHON"),
                         "Set the released baseline interpreter and source for compatibility")
    def test_released_product_uses_its_original_duckdb_and_complete_cache(self):
        source = Path(os.environ["DEFEATBETA_BENCHMARK_BASELINE_SOURCE"]).resolve()
        python = os.environ["DEFEATBETA_BENCHMARK_BASELINE_PYTHON"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}, {"ticker": "BABA"}],
                                      {"price": {"call": "price", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server:
                env = {**os.environ, "PYTHONPATH": str(common.ROOT),
                       "SSL_CERT_FILE": server["certificate"],
                       "REQUESTS_CA_BUNDLE": server["certificate"],
                       "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}
                dependencies = json.loads(subprocess.check_output([python, "-c",
                    "import json; from benchmark.common import environment_info; print(json.dumps(environment_info()['dependencies']))"],
                    cwd=source, env=env, text=True))
                self.assertEqual(dependencies["duckdb"], "1.5.3")
                for index, phase in enumerate([plan.phases()[0], plan.phases()[1], plan.phases()[-1]]):
                    payload = {"source": str(source), "source_hashes": common.source_hashes(source),
                               "dependencies": dependencies, "endpoint": server["url"],
                               "action": "measure", "plan": workload, "phase": phase,
                               "cache_directory": str(directory / f"baseline-{index}")}
                    result = subprocess.run([python, "-m", "benchmark.worker"], cwd=source, env=env,
                        input=json.dumps(payload), capture_output=True, text=True, timeout=180)
                    marker = "BENCHMARK_RESULT="
                    outcome = json.loads(next(line[len(marker):] for line in result.stdout.splitlines()
                                              if line.startswith(marker)))
                    progress = directory / "progress.jsonl"
                    self.assertEqual(outcome["status"], "complete",
                                     (phase, outcome, progress.read_text() if progress.exists() else result.stderr))
                    self.assertEqual(outcome["completed_tasks"], 2)
                    if phase["state"] == "cached":
                        self.assertEqual(outcome["cache_misses"], 0)
                        self.assertEqual(outcome["cache_seed"]["strategy"], "complete_files")

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
