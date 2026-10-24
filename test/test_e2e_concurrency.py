"""Verify orchestration and the report of the paired end-to-end concurrency comparison."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.e2e_concurrency import case_order, mismatches, render, run
from benchmark.e2e import plan


def workload():
    return plan.build_plan(
        [{"ticker": "AAPL", "financial_currency": "USD"},
         {"ticker": "MSFT", "financial_currency": "GBP"}],
        {"currency": {"call": "currency", "kwargs": {"symbol": "EUR=X"}},
         "news_body": {"call": "news.get_news", "kwargs": {}}},
        bodies={"AAPL": {"news_body": {"uuid": "apple-news"}},
                "MSFT": {"news_body": {"uuid": "microsoft-news"}}})


class TestE2EConcurrencyOrchestration(unittest.TestCase):
    def test_case_order_balances_versions_and_concurrencies(self):
        self.assertEqual(case_order(0), [(1, "baseline"), (1, "candidate"),
                                        (4, "candidate"), (4, "baseline"),
                                        (16, "baseline"), (16, "candidate"),
                                        (64, "candidate"), (64, "baseline")])
        self.assertEqual(case_order(1), [(64, "baseline"), (64, "candidate"),
                                        (16, "candidate"), (16, "baseline"),
                                        (4, "baseline"), (4, "candidate"),
                                        (1, "candidate"), (1, "baseline")])
        for workers in (1, 4, 16, 64):
            first = [order[[n for n, _ in order].index(workers)][1]
                     for order in (case_order(0), case_order(1))]
            self.assertEqual(sorted(first), ["baseline", "candidate"], workers)

    def test_orchestration_freezes_one_plan_and_retains_failures(self):
        frozen = workload()
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "new"
                output.mkdir()
                (output / "experiment.json").write_text(json.dumps({"harness": {}, "environments": {
                    "baseline": {"commit": "old"}, "candidate": {"commit": "new"}}}), encoding="utf-8")
                requests = []
                caches = {}

                def execute(experiment, environment, request, destination, timeout):
                    if request["action"] == "discover":
                        return {"status": "complete", "plan": frozen}
                    requests.append(request)
                    key = (environment["commit"], request["phase"]["concurrency"])
                    if request["phase"]["state"] == "cold":
                        cache = destination / "cache"
                        cache.mkdir(parents=True)
                        (cache / "retained.block").write_text(str(key), encoding="utf-8")
                        caches[key] = cache
                    else:
                        cache = Path(request["reuse_cache_directory"])
                        self.assertEqual(cache, caches[key])
                        self.assertEqual((cache / "retained.block").read_text(encoding="utf-8"), str(key))
                    return {"status": "query_errors" if failed else "complete", "wall_seconds": 1,
                            "observed_dataset": {}, "results": [
                                {**task, "status": "ok", "fingerprint": {"sha256": task["id"]}}
                                for task in plan.tasks(request["plan"])]}

                args = SimpleNamespace(output=output, timeout=60, rounds=2)
                with patch("benchmark.e2e_concurrency.prepare", return_value=output), patch(
                        "benchmark.e2e_concurrency.verify_harness"), patch(
                        "benchmark.e2e_concurrency.execute", side_effect=execute):
                    if failed:
                        with self.assertRaises(RuntimeError):
                            run(args)
                    else:
                        run(args)
                saved = json.loads((output / "results.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["status"], "failed" if failed else "complete")
                self.assertEqual(len(saved["records"]), 1 if failed else 16)
                self.assertEqual(saved["concurrencies"], [1, 4, 16, 64])
                self.assertTrue(all(r["plan"]["sha256"] == frozen["sha256"] for r in requests))
                self.assertTrue(all("diagnostics" not in r for r in requests))
                self.assertEqual([r["phase"]["state"] for r in requests],
                                 ["cold"] * (1 if failed else 8) + ([] if failed else ["disk_reuse"] * 8))
                self.assertTrue((output / "results.md").is_file())
                if not failed:
                    self.assertEqual(len(set(caches.values())), 8)
                    self.assertEqual([r["phase"]["concurrency"] for r in requests],
                                     [n for round_index in range(2) for n, _ in case_order(round_index)])

    def test_instrumented_measurements_are_rejected(self):
        frozen = workload()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "experiment.json").write_text(json.dumps({"harness": {}, "environments": {
                "baseline": {"commit": "old"}, "candidate": {"commit": "new"}}}), encoding="utf-8")

            def execute(experiment, environment, request, destination, timeout):
                if request["action"] == "discover":
                    return {"status": "complete", "plan": frozen}
                return {"status": "complete", "wall_seconds": 1, "observed_dataset": {},
                        "results": [], "diagnostics": {}}

            with patch("benchmark.e2e_concurrency.prepare", return_value=output), patch(
                    "benchmark.e2e_concurrency.verify_harness"), patch(
                    "benchmark.e2e_concurrency.execute", side_effect=execute):
                with self.assertRaisesRegex(RuntimeError, "instrumentation"):
                    run(SimpleNamespace(output=output, timeout=60, rounds=2))

    def test_disk_reuse_comparison_requires_exactly_two_rounds(self):
        with patch("benchmark.e2e_concurrency.prepare") as prepare:
            for rounds in (1, 3):
                with self.subTest(rounds=rounds), self.assertRaisesRegex(ValueError, "two rounds"):
                    run(SimpleNamespace(rounds=rounds))
            prepare.assert_not_called()

    def test_result_changes_remain_explicit(self):
        rows = lambda value: {"measurement": {"results": [{"id": "task", "status": "ok", "fingerprint": value}]}}
        self.assertEqual(mismatches([rows("a"), rows("a")]), [])
        self.assertEqual(mismatches([rows("a"), rows("b")]), ["task"])


class TestE2EConcurrencyReport(unittest.TestCase):
    def report(self, records=()):
        return {"status": "complete", "rounds": 2, "plan": workload(), "concurrencies": [1, 4, 16],
                "cache_states": {"1": "cold", "2": "disk_reuse"},
                "experiment": {"environments": {}}, "records": list(records), "mismatched_task_ids": []}

    def record(self, round_number=1, variant="candidate", workers=16, seconds=2.0, digest="a", hits=1549):
        return {"round": round_number, "variant": variant, "concurrency": workers,
                "cache_state": "cold" if round_number == 1 else "disk_reuse",
                "cache_source_case": None if round_number == 1 else f"case-1-{workers}-{variant}",
                "measurement": {
                    "status": "complete", "wall_seconds": seconds, "initialization_seconds": .25,
                    "preparation_seconds": 0, "expected_tasks": 4, "completed_tasks": 4,
                    "failed_tasks": 0, "successful_calls_per_second": 4 / seconds,
                    "requests": {"metrics": {"cache_hits": hits, "cache_misses": 1411,
                                             "downloaded_bytes": 360040137, "range_requests": 1427,
                                             "range_seconds": 388.23886530799774}},
                    "results": [{"id": '["AAPL","currency"]', "symbol": "AAPL", "method": "currency",
                                 "status": "ok", "fingerprint": {"rows": 1, "columns": ["value"],
                                                                 "sha256": digest}}]}}

    def full_report(self):
        records = [self.record(r, v, n, seconds=(8.0 if v == "baseline" else 2.0) * r, hits=r * 100 + n)
                   for r in (2, 1) for n in (16, 4, 1) for v in ("candidate", "baseline")]
        return self.report(records)

    def test_rounds_are_separate_sections_in_order(self):
        text = render(self.full_report())
        first = text.index("## Round 1: cold start")
        second = text.index("## Round 2: reuse the round 1 disk cache")
        self.assertLess(first, second)
        self.assertLess(text.index("### Round 1 downloads"), second)

    def test_timing_rows_pair_baseline_before_candidate_by_worker_count(self):
        text = render(self.full_report())
        round_one = text[text.index("## Round 1"):text.index("## Round 2")]
        rows = [line for line in round_one.splitlines() if line.startswith("| ") and "x |" in line]
        self.assertEqual([row.split(" | ")[0] for row in rows], ["| 1", "| 4", "| 16"])
        self.assertIn("| Workers | Baseline seconds | Candidate seconds | Speedup |", round_one)
        self.assertIn("| 1 | 8.000 | 2.000 | 4.00x | 0.500 | 2.000 | 0 / 0 | complete / complete |", round_one)
        round_two = text[text.index("## Round 2"):]
        self.assertIn("| 16 | 16.000 | 4.000 | 4.00x |", round_two)

    def test_download_rows_list_baseline_then_candidate(self):
        text = render(self.full_report())
        section = text[text.index("### Round 2 downloads"):text.index("## Output equivalence")]
        rows = [line for line in section.splitlines() if line.startswith("| baseline") or line.startswith("| candidate")]
        self.assertEqual([tuple(row.split(" | ")[:2]) for row in rows],
                         [("| baseline", "1"), ("| baseline", "4"), ("| baseline", "16"),
                          ("| candidate", "1"), ("| candidate", "4"), ("| candidate", "16")])
        self.assertIn("| baseline | 4 | 204 | 1411 | 360040137 | 1427 | 388.239 |", section)

    def test_report_omits_constant_noise_columns(self):
        text = render(self.full_report())
        for absent in ("Worker PID", "Preparation seconds", "Configured disk limit", "Peak RSS",
                       "Largest cumulative API durations"):
            self.assertNotIn(absent, text)

    def test_execution_order_is_kept_in_collapsed_details(self):
        report = self.full_report()
        text = render(report)
        section = text[text.index("<summary>Execution order</summary>"):]
        self.assertIn("| 1 | 2 | candidate | 16 | Disk reuse (round 1) | case-1-16-candidate | 0.250 | complete |",
                      section)
        self.assertIn("| 12 | 1 | baseline | 1 | Cold (empty files) | none | 0.250 | complete |", section)

    def test_missing_and_incomplete_batches_have_no_speedup(self):
        records = [self.record(1, "baseline", 1, seconds=8.0)]
        failed = self.record(1, "candidate", 1)
        failed["measurement"] = {"status": "timeout"}
        report = self.report(records + [failed])
        report["status"] = "failed"
        text = render(report)
        self.assertIn("Status: failed", text)
        self.assertIn("| 1 | 8.000 | unavailable | unavailable | 0.500 | unavailable | 0 / unavailable | "
                      "complete / timeout |", text)
        self.assertIn("| 4 | unavailable | unavailable | unavailable | unavailable | unavailable | "
                      "unavailable / unavailable | not run / not run |", text)
        self.assertIn("| candidate | 1 | unavailable | unavailable | unavailable | unavailable | unavailable |", text)

    def test_empty_report_renders(self):
        text = render(self.report())
        self.assertIn("Status: complete", text)
        self.assertIn("Recorded batches: 0", text)

    def test_method_lists_frozen_workload_and_resolved_parameters(self):
        report = self.report()
        text = render(report)
        self.assertIn("2 tickers x 2 query operations = 4 tasks per batch", text)
        self.assertIn(report["plan"]["sha256"], text)
        for value in ("currency", "news.get_news", "EUR=X", "GBP=X", "apple-news", "microsoft-news",
                      "Excel export", "Diagnostic output", "Do not average the two rounds",
                      "Batch seconds exclude", "row order", "floating-point"):
            self.assertIn(value, text)

    def test_missing_source_body_is_listed_without_removing_the_task(self):
        report = self.report()
        frozen = report["plan"]
        del frozen["bodies"]["AAPL"]["news_body"]
        frozen["sha256"] = plan.checksum({key: value for key, value in frozen.items() if key != "sha256"})
        text = render(report)
        self.assertIn("4 tasks per batch", text)
        self.assertIn("AAPL: `not applicable: No source record available during discovery`", text)

    def test_changed_fingerprints_group_distinct_results_by_version(self):
        report = self.report([self.record(2, "candidate", 1, digest="new-digest"),
                              self.record(1, "candidate", 4, digest="new-digest"),
                              self.record(1, "baseline", 4, digest="old-digest"),
                              self.record(2, "baseline", 16, digest="new-digest"),
                              self.record(1, "baseline", 1, digest="old-digest")])
        report["mismatched_task_ids"] = mismatches(report["records"])
        text = render(report)
        rows = [line for line in text.splitlines() if line.startswith("| AAPL | currency |")]
        self.assertEqual(rows, [
            "| AAPL | currency | baseline | 1 | `old-digest` | 1/1, 1/4 |",
            "| AAPL | currency | baseline | 1 | `new-digest` | 2/16 |",
            "| AAPL | currency | candidate | 1 | `new-digest` | 1/4, 2/1 |"])
        self.assertIn("Tasks with changed output fingerprints across batches: 1.", text)


if __name__ == "__main__":
    unittest.main()
