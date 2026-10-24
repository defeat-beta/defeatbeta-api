"""Exercise real query caches through a fixed-data service without timing claims."""

from contextlib import redirect_stdout
import io
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.support.adapter import dataset_endpoint
from benchmark.e2e.backend import ProductBackend
from benchmark.e2e import execution, plan
from benchmark.support.fixture import generate
from benchmark.support.server import serve_fixture
from benchmark import common


class TestWorkerFailures(unittest.TestCase):
    def test_initialization_errors_fail_the_batch_with_the_original_error(self):
        from benchmark.worker import run, worker_error

        workload = plan.build_plan([{"ticker": "PDD"}], {"price": {"call": "price", "kwargs": {}}})
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(ProductBackend, "ticker", side_effect=RuntimeError("Expected initialization failure")):
            with self.assertRaises(RuntimeError) as caught:
                run({"source": str(common.ROOT), "source_hashes": common.source_hashes(),
                     "dependencies": common.environment_info()["dependencies"], "action": "measure",
                     "plan": workload, "cache_directory": temporary,
                     "phase": {"kind": "throughput", "state": "cold", "concurrency": 1}})
        result = worker_error(caught.exception)
        self.assertEqual(result["status"], "worker_error")
        self.assertIn("Expected initialization failure", json.dumps(result))

    def test_non_throughput_phases_are_rejected(self):
        from benchmark.worker import run

        workload = plan.build_plan([{"ticker": "PDD"}], {"price": {"call": "price", "kwargs": {}}})
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(ProductBackend, "ticker", side_effect=AssertionError("Unexpected initialization")):
            with self.assertRaisesRegex(ValueError, "throughput"):
                run({"source": str(common.ROOT), "source_hashes": common.source_hashes(),
                     "dependencies": common.environment_info()["dependencies"], "action": "measure",
                     "plan": workload, "cache_directory": temporary,
                     "phase": {"kind": "latency", "state": "cold", "concurrency": 1}})


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for cache integration")
class TestE2ECacheIntegration(unittest.TestCase):
    def test_second_process_reuses_the_first_process_disk_cache(self):
        from benchmark.benchmark import export_source

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            sources = {"candidate": common.ROOT}
            available = subprocess.run(["git", "rev-parse", "--verify", "release-0.0.62^{commit}"],
                                       cwd=common.ROOT, capture_output=True)
            if available.returncode == 0:
                sources["baseline"] = directory / "baseline-source"
                export_source("release-0.0.62", sources["baseline"])
            workload = plan.build_plan([{"ticker": "PDD"}, {"ticker": "BABA"}],
                                      {"price": {"call": "price", "kwargs": {}}})
            dependencies = common.environment_info()["dependencies"]
            with serve_fixture(directory / "fixture", directory) as server:
                env = {**os.environ, "PYTHONPATH": str(common.ROOT),
                       "SSL_CERT_FILE": server["certificate"], "REQUESTS_CA_BUNDLE": server["certificate"],
                       "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}
                for variant, source in sources.items():
                    with self.subTest(variant=variant):
                        cache = directory / variant / "first" / "cache"
                        outcomes = []
                        retained = {}
                        for state in ("cold", "disk_reuse"):
                            payload = {"source": str(source), "source_hashes": common.source_hashes(source),
                                "dependencies": dependencies, "endpoint": server["url"],
                                "action": "measure", "plan": workload,
                                "phase": {"kind": "throughput", "state": state, "concurrency": 4},
                                "cache_directory": str(cache if state == "cold" else
                                                       directory / variant / "second" / "cache")}
                            if state == "disk_reuse":
                                payload["reuse_cache_directory"] = str(cache)
                            result = subprocess.run([sys.executable, "-m", "benchmark.worker"], cwd=source,
                                env=env, input=json.dumps(payload), capture_output=True, text=True, timeout=90)
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                            marker = "BENCHMARK_RESULT="
                            outcome = json.loads(next(line[len(marker):] for line in result.stdout.splitlines()
                                                      if line.startswith(marker)))
                            self.assertEqual(outcome["successful_tasks"], 2)
                            self.assertNotIn("diagnostics", outcome)
                            outcomes.append(outcome)
                            if state == "cold":
                                retained = {path: path.read_bytes() for path in (cache / "active-cache").iterdir()
                                            if path.suffix in (".block", ".footer")}
                                self.assertTrue(retained)
                                self.assertGreater(outcome["requests"]["metrics"]["downloaded_bytes"], 0)
                        self.assertEqual([row["fingerprint"] for row in outcomes[0]["results"]],
                                         [row["fingerprint"] for row in outcomes[1]["results"]])
                        self.assertGreater(outcomes[1]["requests"]["metrics"]["cache_hits"], 0)
                        self.assertTrue(all(path.read_bytes() == content for path, content in retained.items()))
                        self.assertFalse((directory / variant / "second" / "cache").exists())

    def test_download_failure_preserves_the_original_range_exception(self):
        import httpx
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
        from defeatbeta_api.client.shared_resources import close_network_resources
        from benchmark.worker import worker_error

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}], {"price": {"call": "price", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server, \
                    dataset_endpoint(server["url"]), redirect_stdout(io.StringIO()), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": server["certificate"],
                        "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}):
                original = DatasetCacheFileSystem._request_range

                def fail(filesystem, url, start, end, *args, **kwargs):
                    if url.endswith("stock_prices.parquet") and start > 0:
                        raise httpx.ReadTimeout("Expected asynchronous range timeout")
                    return original(filesystem, url, start, end, *args, **kwargs)

                backend = ProductBackend(directory / "cache", workload)
                try:
                    with patch.object(DatasetCacheFileSystem, "_request_range", fail):
                        try:
                            result = execution.measure_throughput(workload, backend, "cold", 4)
                        except RuntimeError as exc:
                            evidence = worker_error(exc)["preparation"]
                        else:
                            self.assertEqual(result["status"], "query_errors")
                            evidence = result
                    event = evidence["requests"]["errors"][0]
                    self.assertEqual(event["file"], "stock_prices.parquet")
                    self.assertEqual(event["error_type"], "ReadTimeout")
                    self.assertEqual(event["error"], "Expected asynchronous range timeout")
                finally:
                    backend.close()
                    close_network_resources()

    def test_company_catalog_keeps_metadata_probes_separate_from_misses(self):
        from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
        from defeatbeta_api.client.shared_resources import close_network_resources

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory / "fixture")
            workload = plan.build_plan([{"ticker": "PDD"}],
                                      {"catalog": {"call": "catalog", "kwargs": {}}})
            with serve_fixture(directory / "fixture", directory) as server, \
                    dataset_endpoint(server["url"]), redirect_stdout(io.StringIO()), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": server["certificate"],
                        "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}):
                resolve = HuggingFaceClient.resolve_cdn_info

                def without_json_size(client, url, *args, **kwargs):
                    target, size = resolve(client, url, *args, **kwargs)
                    return target, None if url.endswith(".json") else size

                backend = ProductBackend(directory / "cache", workload)
                original_ticker = backend.ticker

                def ticker(symbol):
                    product = original_ticker(symbol)
                    return SimpleNamespace(catalog=product.company_meta.get_all_companies_info)

                try:
                    with patch.object(HuggingFaceClient, "resolve_cdn_info", without_json_size), \
                            patch.object(backend, "ticker", ticker):
                        cold = execution.measure_throughput(workload, backend, "cold", 16)
                        reused = execution.measure_throughput(workload, backend, "disk_reuse", 16)
                    self.assertEqual(cold["status"], "complete", cold)
                    self.assertEqual(reused["status"], "complete", reused)
                    probes = [event for event in cold["requests"]["events"] if event["purpose"] == "size_probe"]
                    self.assertEqual(len(probes), 1)
                    self.assertEqual((probes[0]["file"], probes[0]["start"], probes[0]["end"]),
                                     ("company_tickers.json", 0, 0))
                    self.assertGreater(cold["cache_misses"], 0)
                    self.assertEqual(reused["cache_misses"], 0)
                finally:
                    backend.close()
                    close_network_resources()

    def test_cold_batch_downloads_and_disk_reuse_hits_local_cache(self):
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
                    for concurrency in (1, 4, 16):
                        cold = execution.measure_throughput(workload, backend, "cold", concurrency)
                        self.assertEqual(cold["status"], "complete", cold)
                        self.assertGreater(cold["cache_misses"], 0)
                        reused = execution.measure_throughput(workload, backend, "disk_reuse", concurrency)
                        self.assertEqual(reused["status"], "complete", reused)
                        self.assertEqual(reused["cache_misses"], 0)
                        self.assertEqual({row["id"] for row in reused["results"]},
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
                                      "kind": "throughput", "state": "cold", "concurrency": 1}})
                finally:
                    close_network_resources()
            self.assertEqual(result["status"], "complete", result)
            self.assertEqual(result["results"][0]["fingerprint"]["rows"], 32768)
            self.assertTrue(result["observed_dataset"]["footer_index"])
            self.assertIn("dcf_data", result["api_coverage"])
