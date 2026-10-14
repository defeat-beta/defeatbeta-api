"""Contract and real TLS integration tests for the paired benchmark framework."""

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
import pandas as pd

from benchmark import benchmark, common, fixture, report, suite
from benchmark.adapter import dataset_endpoint
from benchmark.server import RangeApplication, serve_fixture
from benchmark.worker import run


def fake_record(mode="controlled", rounds=6):
    cases = [{"id": "price.first_use", "kind": "single", "state": "first_use"}]
    records = []
    for number in range(1, rounds + 1):
        for variant, seconds in (("baseline", 2.0), ("candidate", 1.0)):
            measurement = {"status": "ok", "dataset_version": "v1", "file_metadata": {},
                "first_result_seconds": seconds, "wall_seconds": seconds - .1,
                "completed_calls_per_second": 1 / seconds, "latency": {"p95_seconds": seconds},
                "cpu_seconds": .1, "rss_bytes_at_query_end": 1024, "pool_after": None,
                "cache_total_delta": {"downloaded_bytes": 100, "range_requests": 1},
                "results": [{"task": {"symbol": "AAPL", "method": "price"},
                             "result": {"rows": 1, "sha256": "same"}}]}
            records.append({"case": cases[0]["id"], "round": number, "variant": variant, "measurement": measurement})
    return {"schema_version": 1, "status": "complete", "mode": mode, "rounds": rounds, "records": records,
            "suite": {"cases": cases, "name": "test", "version": 1}, "network": "Loopback",
            "experiment": {"environments": {name: {"commit": name, "environment": {
                "dependencies": {"duckdb": "2"}, "python": "3.11", "platform": "test",
                "cpu_count": 4, "ram_bytes": 1000}} for name in ("baseline", "candidate")}}}


class TestBenchmarkContract(unittest.TestCase):
    def test_suite_is_deterministic_and_broad(self):
        self.assertEqual(suite.make_suite(), suite.make_suite())
        self.assertNotEqual(suite.make_suite(seed=1)["sha256"], suite.make_suite(seed=2)["sha256"])
        plan = suite.make_suite()
        self.assertEqual(len(plan["symbols"]), 32)
        self.assertEqual({case["state"] for case in plan["cases"]}, set(suite.STATES))
        self.assertTrue({"price", "info", "transcript_body", "market_capitalization", "quarterly_income_statement"}.issubset(plan["methods"]))
        self.assertEqual(len({case["id"] for case in plan["cases"]}), len(plan["cases"]))

    def test_stream_work_is_identical_at_every_concurrency(self):
        cases = [case for case in suite.make_suite()["cases"] if case["kind"] == "stream"]
        self.assertEqual({case["concurrency"] for case in cases}, {1, 4, 16, 64, 128})
        self.assertTrue(all(case["tasks"] == cases[0]["tasks"] for case in cases))
        for case in suite.make_suite()["cases"]:
            if case["kind"] == "burst":
                self.assertEqual(len(case["tasks"]), case["concurrency"])

    def test_order_balances_every_case(self):
        for case in range(12):
            orders = [benchmark.paired_order(number, case) for number in range(6)]
            self.assertEqual(orders.count(("baseline", "candidate")), 3)
            self.assertEqual(orders.count(("candidate", "baseline")), 3)

    def test_row_multiset_preserves_duplicates_and_ignores_row_order(self):
        a = pd.DataFrame({"symbol": ["A", "B", "B"], "value": [1, 2, 2]})
        self.assertEqual(common.result_fingerprint(a), common.result_fingerprint(a.iloc[::-1]))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.drop_duplicates()))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.rename(columns={"value": "price"})))

    def test_nested_values_are_canonical(self):
        a = pd.DataFrame({"body": [[{"a": 1, "b": [2, 3]}]]})
        b = pd.DataFrame({"body": [[{"b": [2, 3], "a": 1}]]})
        self.assertEqual(common.result_fingerprint(a), common.result_fingerprint(b))

    def test_secret_redaction(self):
        value = common.redact_secrets({"proxy": "socks5://name:secret@localhost:100", "url": "https://cdn.test/file?secret=abc"})
        self.assertNotIn("name:secret", json.dumps(value))
        self.assertNotIn("secret=abc", json.dumps(value))

    def test_controlled_route_removes_proxy_without_touching_parent(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy:80", "HTTPS_PROXY": "http://proxy:80"}):
            env = benchmark.worker_environment(Path("/experiment"), Path("/source"), {"certificate": "/cert"})
            self.assertNotIn("HTTP_PROXY", env)
            self.assertEqual(env["SSL_CERT_FILE"], "/cert")
            self.assertEqual(os.environ["HTTP_PROXY"], "http://proxy:80")

    def test_missing_result_never_counts_as_success(self):
        value = fake_record()
        value["records"].pop()
        self.assertFalse(report.summarize(value)["valid"])

    def test_nonfinite_times_never_count_as_success(self):
        for seconds in (float("nan"), float("inf"), -1, 0):
            with self.subTest(seconds=seconds):
                value = fake_record()
                value["records"][0]["measurement"]["first_result_seconds"] = seconds
                self.assertFalse(report.summarize(value)["valid"])

    def test_undeclared_sample_never_counts_as_success(self):
        for field, replacement in (("case", "undeclared"), ("round", 7), ("variant", "other")):
            with self.subTest(field=field):
                value = fake_record()
                sample = deepcopy(value["records"][0])
                sample[field] = replacement
                value["records"].append(sample)
                self.assertFalse(report.summarize(value)["valid"])

    def test_empty_suite_or_missing_fingerprints_is_invalid(self):
        value = fake_record()
        value["suite"]["cases"] = []
        value["records"] = []
        self.assertFalse(report.summarize(value)["valid"])
        value = fake_record()
        for sample in value["records"]:
            sample["measurement"]["results"] = []
        self.assertFalse(report.summarize(value)["valid"])

    def test_parent_and_prepared_harness_must_match(self):
        for content in (b"original\n", b"original\r\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                current, prepared = root / "current", root / "prepared"
                current.mkdir()
                prepared.mkdir()
                for folder in (current, prepared):
                    (folder / "worker.py").write_bytes(content)
                expected = {"worker.py": hashlib.sha256(content).hexdigest()}
                benchmark.verify_harness(current, prepared, expected)
                (current / "worker.py").write_bytes(content + b"changed\n")
                with self.assertRaisesRegex(ValueError, "harness changed"):
                    benchmark.verify_harness(current, prepared, expected)

    def test_failure_and_duplicate_are_not_dropped(self):
        value = fake_record()
        value["records"][1]["measurement"]["status"] = "timeout"
        value["records"].append(deepcopy(value["records"][0]))
        summary = report.summarize(value)
        self.assertFalse(summary["valid"])
        self.assertEqual(summary["cases"][0]["classification"], "invalid")

    def test_live_daily_updates_are_accepted_and_labeled(self):
        value = fake_record("live")
        value["records"][1]["measurement"]["dataset_version"] = "v2"
        value["records"][1]["measurement"]["results"][0]["result"]["sha256"] = "updated-data"
        summary = report.summarize(value)
        self.assertTrue(summary["valid"])
        self.assertTrue(summary["cases"][0]["notes"])
        self.assertEqual(summary["cases"][0]["classification"], "inconclusive")

    def test_same_data_result_mismatch_is_invalid(self):
        for mode in ("controlled", "live"):
            value = fake_record(mode)
            value["records"][1]["measurement"]["results"][0]["result"]["sha256"] = "wrong"
            self.assertFalse(report.summarize(value)["valid"])

    def test_paired_change_and_small_sample_limit(self):
        summary = report.summarize(fake_record())
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["cases"][0]["paired_latency_reduction_percent"], 50)
        self.assertEqual(summary["cases"][0]["classification"], "faster in this run")
        self.assertEqual(report.summarize(fake_record(rounds=1))["cases"][0]["classification"], "inconclusive")

    def test_render_does_not_execute_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            common.save_json(path, fake_record())
            with patch.object(benchmark, "execute", side_effect=AssertionError("No requests allowed")):
                report.render(path)
            content = path.with_suffix(".md").read_text()
            self.assertIn("50.0", content)
            self.assertIn("n/a", content)
            self.assertIn("results.json", content)

    def test_worker_rejects_wrong_source_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "escaped"):
            run({"source": "/wrong-source"})

    def test_worker_rejects_mutated_source_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "sources changed"):
            run({"source": str(common.ROOT), "source_hashes": {}})

    def test_timeout_is_retained(self):
        with patch("benchmark.benchmark.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 3)):
            value = benchmark.execute(Path("/experiment"), {"source": "/source", "source_hashes": {},
                "python": "python", "environment": {"dependencies": {}}}, {}, Path("/cache"), 3)
        self.assertEqual(value["status"], "timeout")
        self.assertEqual(value["timeout_seconds"], 3)


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for real fixture integration")
class TestBenchmarkTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.fixture = cls.directory / "fixture"
        cls.identity = fixture.generate(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_generator_checksums_and_independent_price_reference(self):
        import duckdb
        verified = fixture.verify(self.fixture)
        self.assertEqual(verified, self.identity)
        with duckdb.connect() as con:
            row = con.execute("SELECT count(*), min(close), max(close) FROM read_parquet(?) WHERE symbol='PDD'",
                              [str(self.fixture / "stock_prices.parquet")]).fetchone()
        self.assertEqual(row, (32768, 50.0, 59.99))
        target = self.fixture / "stock_profile.parquet"
        original = target.read_bytes()
        try:
            target.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                fixture.verify(self.fixture)
        finally:
            target.write_bytes(original)

    def test_real_tls_protocol_range_and_product_states(self):
        for protocol in ("h2", "http1"):
            with self.subTest(protocol=protocol), serve_fixture(self.fixture, self.directory, protocol) as server:
                context = ssl.create_default_context(cafile=server["certificate"])
                with httpx.Client(verify=context, trust_env=False, http2=True) as http:
                    response = http.get(server["url"] + "/data/stock_prices.parquet", headers={"Range": "bytes=0-3"})
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(response.content, b"PAR1")
                    self.assertEqual(response.http_version, server["protocol"])
                    self.assertEqual(http.get(server["url"] + "/data/stock_prices.parquet", headers={"Range": "bytes=8-4"}).status_code, 416)
                # Exercise fresh interpreters to verify disk reuse and avoid shared test state.
                experiment = self.directory / ("experiment-" + protocol)
                (experiment / "harness").mkdir(parents=True)
                (experiment / "harness" / "benchmark").symlink_to(common.ROOT / "benchmark", target_is_directory=True)
                environment = {"python": sys.executable, "source": str(common.ROOT),
                               "source_hashes": common.source_hashes(), "environment": common.environment_info()}
                cache = experiment / "cache"
                cache.mkdir()
                for state in ("first_use", "disk_warm", "metadata_ready", "memory_warm"):
                    if state != "disk_warm":
                        case_cache = cache if state == "first_use" else experiment / state
                        case_cache.mkdir(exist_ok=True)
                    case = {"id": state, "kind": "single", "state": state, "concurrency": 1,
                            "tasks": [{"symbol": "PDD", "method": "price"}]}
                    value = benchmark.execute(experiment, environment, case, case_cache, 90, server)
                    self.assertEqual(value["status"], "ok", value)
                    self.assertEqual(value["results"][0]["result"]["rows"], 32768)
                    if state in ("memory_warm", "disk_warm"):
                        self.assertEqual(value["cache_query_delta"]["downloaded_bytes"], 0)
                    if state == "memory_warm":
                        observed = {**case, "diagnostics": {"memory": True, "profile_repeats": 3}}
                        measured = benchmark.execute(experiment, environment, observed, case_cache, 90, server)
                        self.assertEqual(measured["status"], "ok", measured)
                        self.assertEqual(measured["results"][0]["result"], value["results"][0]["result"])
                        self.assertEqual(measured["cache_total_delta"]["range_requests"], 0)
                        self.assertEqual(measured["results"][0]["profile"]["repetitions"], 3)
                        self.assertEqual([item["stage"] for item in measured["diagnostics"]["memory"]], [
                            "before_constructor", "before_query", "after_query_and_drain",
                            "after_results_released", "after_client_closed"])
