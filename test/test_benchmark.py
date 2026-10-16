"""Protect paired orchestration, evidence validation, and fixed-data correctness."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx
import pandas as pd

from benchmark import benchmark, common, report
from benchmark.support import fixture
from benchmark.e2e import plan
from benchmark.e2e.execution import MAX_CACHE_PREPARATION_PASSES
from benchmark.support.server import serve_fixture


def fake_record(rounds=6, baseline=True):
    workload = plan.build_plan([{"ticker": "AAPL"}, {"ticker": "PDD"}],
                               {"price": {"call": "price", "kwargs": {}}})
    environments = {name: {"commit": ("a" if name == "baseline" else "b") * 40,
        "source_hashes": {"product.py": "digest"}, "dependency_lock": "product==1\n",
        "environment": {"dependencies": {"duckdb": "2"}, "python": "3.11", "cpu_count": 4}}
        for name in (("baseline", "candidate") if baseline else ("candidate",))}
    record = {"schema_version": 2, "status": "complete", "stage": "development", "rounds": rounds,
              "phases": plan.phases(), "plan": workload, "records": [],
              "workflow": {"repository": "owner/repo", "run_id": "42", "run_attempt": "1", "sha": "c" * 40},
              "experiment": {"environments": environments, "harness": {}, "harness_dependency_lock": "tool==1\n"}}
    for phase in record["phases"]:
        for number in range(1, rounds + 1):
            for variant in environments:
                seconds = 2.0 if variant == "baseline" else 1.0
                rows = [{**{key: task[key] for key in ("id", "symbol", "method", "kwargs")},
                         "status": "ok", "seconds": seconds, "initialization_seconds": .2,
                         "fingerprint": {"sha256": "same", "rows": 1}}
                        for task in plan.tasks(workload)]
                value = {"status": "complete", "results": rows, "completed_tasks": 2,
                         "successful_tasks": 2, "failed_tasks": 0, "not_applicable_tasks": 0,
                         "wall_seconds": seconds, "successful_calls_per_second": 2 / seconds,
                         "cache_misses": 0, "observed_dataset": {"update_time": "same"},
                         "api_coverage": workload["methods"],
                         "cache_settings": {"disk_limit_bytes": 2**60, "memory_limit_bytes": 512,
                                            "native_file_cache": True}}
                if phase["state"] == "cached":
                    def preparation(identifiers):
                        return {"status": "ready", "concurrency": phase["concurrency"],
                                "execution": "caller" if phase["kind"] == "latency" else "thread_pool",
                                "max_passes": MAX_CACHE_PREPARATION_PASSES, "errors": [],
                                "elapsed_seconds": 1.0, "passes": [{"number": 1,
                                    "task_ids": identifiers, "completed_tasks": len(identifiers),
                                    "successful_tasks": len(identifiers), "not_applicable_tasks": 0,
                                    "failed_tasks": 0, "cache_misses": 0, "elapsed_seconds": 1.0}]}
                    if phase["kind"] == "latency":
                        for row in rows:
                            row["cache_preparation"] = preparation([row["id"]])
                    else:
                        value["cache_preparation"] = preparation([row["id"] for row in rows])
                record["records"].append({"phase": phase["id"], "round": number,
                                          "variant": variant, "measurement": value})
    return record


class TestBenchmarkContract(unittest.TestCase):
    def test_cached_report_requires_complete_zero_request_preparation(self):
        mutations = [lambda p: p.update(status="not_ready"),
                     lambda p: p.update(concurrency=128),
                     lambda p: p.update(execution="caller"),
                     lambda p: p.update(passes=[]),
                     lambda p: p["passes"][-1].update(cache_misses=1),
                     lambda p: p["passes"][-1]["task_ids"].pop(),
                     lambda p: p.update(errors=[{"status": "error"}])]
        for mutate in mutations:
            value = fake_record()
            measurement = next(s["measurement"] for s in value["records"]
                               if s["phase"] == "throughput.cached.4")
            mutate(measurement["cache_preparation"])
            self.assertFalse(report.summarize(value)["valid"])

    def test_cached_latency_cannot_omit_its_preparation_evidence(self):
        value = fake_record()
        measurement = next(s["measurement"] for s in value["records"] if s["phase"] == "latency.cached")
        measurement["results"][0].pop("cache_preparation")
        self.assertFalse(report.summarize(value)["valid"])

    def test_timeout_preserves_finished_latency_outcomes(self):
        environment = {"python": "python", "source": "/source", "source_hashes": {},
                       "environment": {"dependencies": {}}}

        def expired(command, **kwargs):
            request = json.loads(kwargs["input"])
            Path(request["progress_path"]).write_text('{"id":"finished"}\n{"id":', encoding="utf-8")
            raise subprocess.TimeoutExpired(command, 1)

        with tempfile.TemporaryDirectory() as directory, patch.object(benchmark.subprocess, "run", side_effect=expired):
            result = benchmark.execute(Path(directory), environment, {}, Path(directory) / "worker", 1)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["completed_tasks"], 1)
        self.assertEqual(result["results"], [{"id": "finished"}])

    def test_query_failures_keep_their_status_and_original_ledger(self):
        response = {"status": "query_errors", "results": [{"id": "failed", "status": "error"}]}
        environment = {"python": "python", "source": "/source", "source_hashes": {},
                       "environment": {"dependencies": {}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(benchmark.subprocess, "run", return_value=
                subprocess.CompletedProcess([], 1, benchmark.MARKER + json.dumps(response), "")):
            value = benchmark.execute(Path(directory), environment, {}, Path(directory) / "cache", 1)
        self.assertEqual(value["status"], "query_errors")
        self.assertEqual(value["results"], response["results"])

    def test_failed_queries_remain_visible_in_readable_reports(self):
        value = fake_record()
        measurement = value["records"][0]["measurement"]
        measurement["status"] = "query_errors"
        measurement["results"][0].update(status="error", error_type="ValueError", error="Expected failure")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            common.save_json(path, value)
            self.assertFalse(report.render(path)["valid"])
            text = path.with_suffix(".md").read_text()
        self.assertIn("ValueError", text)
        self.assertIn("AAPL", text)

    def test_standalone_and_paired_reports_are_valid(self):
        for baseline in (False, True):
            summary = report.summarize(fake_record(baseline=baseline))
            self.assertTrue(summary["valid"], summary["errors"])
            self.assertEqual(len(summary["cases"]), 14)
            self.assertEqual({row["classification"] for row in summary["cases"]},
                             {"faster"} if baseline else {"standalone"})

    def test_all_hit_and_complete_task_ledgers_are_required(self):
        changes = [lambda m: m["results"].pop(),
                   lambda m: m["results"].append(deepcopy(m["results"][0])),
                   lambda m: m.update(successful_tasks=100),
                   lambda m: m["results"][0].update(status="error"),
                   lambda m: m["results"][0].update(kwargs={"extra": 1}),
                   lambda m: m["cache_settings"].update(disk_limit_bytes=1)]
        for change in changes:
            value = fake_record()
            change(value["records"][0]["measurement"])
            self.assertFalse(report.summarize(value)["valid"])
        value = fake_record()
        next(s for s in value["records"] if s["phase"] == "latency.cached")["measurement"]["cache_misses"] = 1
        self.assertFalse(report.summarize(value)["valid"])

    def test_missing_duplicate_and_nonfinite_measurements_are_rejected(self):
        value = fake_record()
        value["records"].pop()
        self.assertFalse(report.summarize(value)["valid"])
        value = fake_record()
        value["records"].append(deepcopy(value["records"][0]))
        self.assertFalse(report.summarize(value)["valid"])
        for seconds in (float("nan"), float("inf"), -1, 0):
            value = fake_record()
            value["records"][0]["measurement"]["results"][0]["seconds"] = seconds
            self.assertFalse(report.summarize(value)["valid"])

    def test_data_change_is_inconclusive_and_same_data_mismatch_is_invalid(self):
        value = fake_record()
        value["records"][0]["measurement"]["observed_dataset"] = {"update_time": "changed"}
        summary = report.summarize(value)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["cases"][0]["classification"], "inconclusive")
        value = fake_record()
        value["records"][0]["measurement"]["results"][0]["fingerprint"] = {"sha256": "wrong"}
        self.assertFalse(report.summarize(value)["valid"])

    def test_short_pairs_do_not_claim_a_speedup(self):
        summary = report.summarize(fake_record(rounds=2))
        self.assertTrue(summary["valid"])
        self.assertEqual({row["classification"] for row in summary["cases"]}, {"inconclusive"})

    def test_standalone_cannot_hide_missing_data_identity_or_api_coverage(self):
        for key in ("observed_dataset", "api_coverage"):
            value = fake_record(baseline=False)
            value["records"][0]["measurement"].pop(key, None)
            self.assertFalse(report.summarize(value)["valid"], key)

    def test_order_balances_each_phase(self):
        for index in range(12):
            self.assertEqual([benchmark.paired_order(n, index) for n in range(6)].count(
                ("baseline", "candidate")), 3)

    def test_hash_preserves_duplicate_rows_column_names_and_nested_values(self):
        a = pd.DataFrame({"symbol": ["A", "B", "B"], "body": [[{"a": 1}], [{"b": 2}], [{"b": 2}]]})
        self.assertEqual(common.result_fingerprint(a), common.result_fingerprint(a.iloc[::-1]))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.drop(index=2)))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.rename(columns={"body": "x"})))

    def test_harness_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worker.py").write_text("# Frozen harness\n")
            expected = benchmark.harness_hashes(root)
            benchmark.verify_harness(root, root, expected)
            (root / "worker.py").write_text("# Modified harness\n")
            with self.assertRaises(ValueError):
                benchmark.verify_harness(root, root, expected)

    def test_collect_requires_all_phases_and_identical_experiments(self):
        value = fake_record(rounds=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for phase in value["phases"]:
                fragment = deepcopy(value)
                fragment["phases"] = [phase]
                fragment["records"] = [s for s in value["records"] if s["phase"] == phase["id"]]
                folder = root / "source" / phase["id"]
                folder.mkdir(parents=True)
                common.save_json(folder / "results.json", fragment)
            target = report.collect(root / "source", root / "complete")
            self.assertTrue(report.render(target)["valid"])
            broken = root / "source" / "latency.cold" / "results.json"
            fragment = json.loads(broken.read_text())
            fragment["workflow"]["run_attempt"] = "2"
            common.save_json(broken, fragment)
            with self.assertRaisesRegex(ValueError, "mixes"):
                report.collect(root / "source", root / "mixed")
            broken.unlink()
            with self.assertRaisesRegex(ValueError, "twelve"):
                report.collect(root / "source", root / "partial")

    def test_secret_redaction(self):
        value = common.redact_secrets({"proxy": "socks5://name:secret@localhost:100", "url": "https://cdn.test/file?secret=abc"})
        self.assertNotIn("name:secret", json.dumps(value))
        self.assertNotIn("secret=abc", json.dumps(value))


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for fixture integration")
class TestBenchmarkTLS(unittest.TestCase):
    def test_fixture_integrity_h2_and_independent_price_reference(self):
        import duckdb

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = fixture.generate(root / "fixture")
            self.assertEqual(fixture.verify(root / "fixture"), identity)
            with duckdb.connect() as con:
                result = con.execute("SELECT count(*), min(close), max(close) FROM read_parquet(?) WHERE symbol='PDD'",
                    [str(root / "fixture" / "stock_prices.parquet")]).fetchone()
            self.assertEqual(result, (32768, 50.0, 59.99))
            with serve_fixture(root / "fixture", root) as server:
                context = ssl.create_default_context(cafile=server["certificate"])
                with httpx.Client(verify=context, trust_env=False, http2=True) as http:
                    response = http.get(server["url"] + "/data/stock_prices.parquet", headers={"Range": "bytes=0-3"})
                    self.assertEqual((response.status_code, response.content, response.http_version),
                                     (206, b"PAR1", "HTTP/2"))
                    self.assertEqual(http.get(server["url"] + "/data/stock_prices.parquet",
                                              headers={"Range": "bytes=8-4"}).status_code, 416)
            path = root / "fixture" / "stock_prices.parquet"
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                fixture.verify(root / "fixture")
