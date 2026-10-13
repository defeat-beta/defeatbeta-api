"""Check the offline dependency reproducer without CPU timing thresholds."""

import tempfile
import multiprocessing
import unittest
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from benchmark.diagnostics.duckdb_wait_repro import _measure_case, create_fixture, run_case
from benchmark.diagnostics import duckdb_wait_repro


class TestDuckDBWaitRepro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            cls.payload = create_fixture(directory)

    def test_delayed_read_preserves_results_and_records_ownership(self):
        for threads in (1, 4):
            with self.subTest(threads=threads):
                case = run_case(self.payload, threads=threads, blocked_seconds=0.1)
                self.assertGreaterEqual(case["blocked_wall_seconds"], 0.1)
                self.assertGreaterEqual(case["blocked_cpu_seconds"], 0)
                self.assertTrue(case["readers_at_end_of_block"][0])
                self.assertEqual(case["results"][0]["status"], "ok")
                self.assertEqual(case["results"][0]["effective_threads"], threads)
                # Thread ownership is an observation, not a DuckDB API contract.
                for reader in case["readers_at_end_of_block"][0]:
                    self.assertIsInstance(reader["caller_owned"], bool)
                    self.assertGreater(reader["native_id"], 0)

    def test_coarse_deadline_clock_does_not_quantize_elapsed_measurements(self):
        with patch("benchmark.diagnostics.duckdb_wait_repro.time.monotonic", return_value=1):
            case = _measure_case(self.payload, threads=4, queries=1, blocked_seconds=0.1, cancel=False)
        self.assertGreaterEqual(case["blocked_wall_seconds"], 0.1)
        self.assertEqual(case["results"][0]["status"], "ok")

    def test_zero_elapsed_time_keeps_results_and_marks_cpu_ratio_unavailable(self):
        with patch("benchmark.diagnostics.duckdb_wait_repro.time.monotonic", return_value=1), \
                patch("benchmark.diagnostics.duckdb_wait_repro.time.perf_counter", return_value=1):
            case = _measure_case(self.payload, threads=4, queries=1, blocked_seconds=0.001, cancel=False)
        self.assertEqual(case["blocked_wall_seconds"], 0)
        self.assertIsNone(case["blocked_cpu_per_wall"])
        self.assertEqual(case["results"][0]["status"], "ok")

    def test_cli_reports_an_unavailable_ratio_without_failing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            output = io.StringIO()
            arguments = ["duckdb_wait_repro", "--output", str(path), "--threads", "1",
                         "--queries", "1", "--delays", "0.001", "--repeats", "1"]
            case = {"blocked_cpu_per_wall": None, "readers_at_end_of_block": [[]]}
            with patch("sys.argv", arguments), redirect_stdout(output), \
                    patch.object(duckdb_wait_repro, "create_fixture", return_value=self.payload), \
                    patch.object(duckdb_wait_repro, "run_case", return_value=case):
                duckdb_wait_repro.main()
            report = json.loads(path.read_text())
            self.assertEqual(report["status"], "complete")
            self.assertIsNone(report["cases"][0]["blocked_cpu_per_wall"])
            self.assertIn("cpu/wall=n/a", output.getvalue())

    def test_concurrent_queries_have_separate_gates_and_correct_results(self):
        for threads in (1, 4):
            with self.subTest(threads=threads):
                case = run_case(self.payload, threads=threads, queries=4, blocked_seconds=0.1)
                self.assertEqual(len(case["results"]), 4)
                self.assertTrue(all(case["readers_at_end_of_block"]))
                self.assertEqual(len({tuple(r["result"]) for r in case["results"]}), 1)
                self.assertTrue(all(r["effective_threads"] == threads for r in case["results"]))

    def test_interrupt_recovers_cursor_without_cancelling_other_query(self):
        for threads in (1, 4):
            with self.subTest(threads=threads):
                case = run_case(self.payload, threads=threads, queries=2, blocked_seconds=0.1, cancel=True)
                self.assertEqual(case["results"][0]["error_type"], "InterruptException")
                self.assertEqual(case["results"][1]["status"], "ok")
                self.assertEqual(case["cancelled_cursor_recovery"], 42)

    def test_parent_deadline_leaves_no_running_child(self):
        before = {child.pid for child in multiprocessing.active_children()}
        with self.assertRaisesRegex(TimeoutError, "deadline"):
            run_case(self.payload, blocked_seconds=0.9, timeout=0.001)
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)


if __name__ == "__main__":
    unittest.main()
