"""Contract tests for the executable performance benchmark."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "benchmark" / "benchmark.py"
REPORT_PATH = ROOT / "benchmark" / "report.py"


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location("defeatbeta_benchmark", BENCHMARK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load benchmark module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_report_module():
    spec = importlib.util.spec_from_file_location("defeatbeta_benchmark_report", REPORT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load report module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkApiContractTests(unittest.TestCase):
    def test_workload_calls_ticker_price(self):
        benchmark = load_benchmark_module()
        calls = []

        class FakeRecorder:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class FakeConfiguration:
            def __init__(self, **kwargs):
                calls.append(("configuration", kwargs))

        class FakeTicker:
            def __init__(self, symbol, **kwargs):
                calls.append(("ticker", symbol, kwargs))

            def price(self):
                calls.append(("price",))
                return FakeFrame()

        class FakeFrame:
            columns = ["symbol"]

            def __len__(self):
                return 1

        api = benchmark.ApiBindings(
            Configuration=FakeConfiguration,
            Ticker=FakeTicker,
            capture_performance=lambda sink: FakeRecorder(),
        )
        with tempfile.TemporaryDirectory() as directory:
            outcome = benchmark.run_api_workload(
                {
                    "symbol": "AAPL",
                    "cache_directory": directory,
                    "http_proxy": "http://127.0.0.1:8118",
                    "configuration": {},
                },
                api=api,
                diagnostics=False,
            )

        self.assertEqual(outcome["status"], "ok")
        self.assertIn(("price",), calls)

    def test_primary_summary_uses_execute_query_time(self):
        benchmark = load_benchmark_module()
        samples = [
            {
                "status": "ok",
                "execute_query_seconds": float(index),
                "api_call_seconds": float(index + 100),
            }
            for index in range(1, 4)
        ]

        summary = benchmark.summarize(samples)

        self.assertEqual(summary["metric"], "execute_query_seconds")
        self.assertEqual(summary["median_seconds"], 2.0)
        self.assertIsNone(summary["p95_seconds"])

    def test_p95_requires_at_least_twenty_samples(self):
        benchmark = load_benchmark_module()
        samples = [
            {"status": "ok", "execute_query_seconds": float(index)}
            for index in range(1, 21)
        ]

        summary = benchmark.summarize(samples)

        self.assertAlmostEqual(summary["p95_seconds"], 19.05)

    def test_persisted_values_redact_urls_and_proxy_credentials(self):
        benchmark = load_benchmark_module()
        value = {
            "url": "https://cdn.example/file.parquet?Signature=secret&Expires=1",
            "proxy": "http://user:password@127.0.0.1:8118",
        }

        redacted = benchmark.redact_secrets(value)

        self.assertNotIn("secret", json.dumps(redacted))
        self.assertNotIn("password", json.dumps(redacted))
        self.assertIn("?<redacted>", redacted["url"])

    def test_worker_imports_the_repository_source_tree_first(self):
        benchmark = load_benchmark_module()

        environment = benchmark.worker_environment(
            {"http_proxy": None}, {"PYTHONPATH": "/existing/path"}
        )

        paths = environment["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(paths[0], str(ROOT))
        self.assertEqual(paths[1], "/existing/path")

    def test_cold_cache_validation_rejects_non_spec_remote_blocks(self):
        benchmark = load_benchmark_module()
        benchmark.validate_cold_cache_status([
            {"original_remote_path": "https://huggingface.co/data/spec.json"},
        ])

        with self.assertRaisesRegex(ValueError, "remote data block"):
            benchmark.validate_cold_cache_status([
                {"original_remote_path": "https://cdn.example/content-hash?<redacted>"},
            ])


class BenchmarkArchiveTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = load_benchmark_module()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def reports(self, tag, suite_id):
        reports = []
        for symbol in ("AAPL", "KDP"):
            result = {"rows": 1, "sha256": symbol}
            samples = [
                {
                    "status": "ok",
                    "execute_query_seconds": 1.0,
                    "api_call_seconds": 1.1,
                    "result": result,
                }
            ]
            reports.append({
                "status": "complete",
                "suite_id": suite_id,
                "suite_symbols": ["AAPL", "KDP"],
                "schedule": "round_robin",
                "tag": tag,
                "symbol": symbol,
                "revision": "main",
                "url": "https://huggingface.co/file.parquet",
                "api_call": "defeatbeta_api.data.ticker.Ticker.price",
                "resolve_direct": True,
                "primary_metric": "execute_query_seconds",
                "requested_runs": 1,
                "timeout_seconds": 600.0,
                "environment": {"duckdb": "1.5.3"},
                "implementation": {"duckdb_client.py": tag},
                "configured_settings": {"http_keep_alive": True},
                "methodology": {"cold": "Isolated local cache"},
                "samples": samples,
                "statistics": self.benchmark.summarize(samples),
            })
        return reports

    def test_archive_round_trip_allows_implementation_change(self):
        baseline = self.root / "baseline.json"
        candidate = self.root / "candidate.json"
        self.benchmark.write_record(
            baseline, self.reports("baseline", "20260923T000000.000000Z_baseline")
        )
        self.benchmark.write_record(
            candidate, self.reports("candidate", "20260923T010000.000000Z_candidate")
        )

        archived = self.benchmark.archive_comparison(
            baseline, candidate, self.root, "002_api_workload"
        )

        record = json.loads(archived.read_text(encoding="utf-8"))
        self.assertEqual(record["format_version"], 3)
        self.assertEqual(len(list((self.root / "archive").glob("*.json"))), 1)


class BenchmarkReportTests(unittest.TestCase):
    def test_existing_archives_still_render(self):
        report = load_report_module()
        sources = [
            ROOT / "benchmark" / "results" / "archive" / "000_baseline.json",
            ROOT / "benchmark" / "results" / "archive" / "001_resolve_once_cdn.json",
        ]
        with tempfile.TemporaryDirectory() as directory:
            for source in sources:
                destination = Path(directory) / f"{source.stem}.md"
                report.render_markdown(source, destination)
                rendered = destination.read_text(encoding="utf-8")
                self.assertIn("Stock Price Cold Query", rendered)
                self.assertIn("Result", rendered)


if __name__ == "__main__":
    unittest.main()
