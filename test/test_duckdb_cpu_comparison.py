"""Verify workload equivalence without machine-dependent performance gates."""

import multiprocessing
import unittest
from unittest.mock import patch

from benchmark.diagnostics.duckdb_cpu_comparison import _measure, expected_result, run_case


class TestDuckDBCPUComparison(unittest.TestCase):
    def test_zero_elapsed_time_keeps_results_and_marks_rate_unavailable(self):
        with patch("benchmark.diagnostics.duckdb_cpu_comparison.time.monotonic", return_value=1), \
                patch("benchmark.diagnostics.duckdb_cpu_comparison.time.perf_counter", return_value=1):
            case = _measure(threads=4, queries=1, rows=63)
        self.assertEqual(case["wall_seconds"], 0)
        self.assertIsNone(case["queries_per_second"])
        self.assertEqual(case["results"][0]["seconds"], 0)
        self.assertEqual(case["rows_per_query"], 63)
        self.assertTrue(case["result_sha256"])

    def test_reference_covers_partial_periods_and_empty_groups(self):
        for rows in (1, 63, 4096, 4097):
            with self.subTest(rows=rows):
                expected = {}
                for index in range(rows):
                    value = index % 4096
                    bucket = expected.setdefault(value % 64, [0, 0])
                    bucket[0] += (value * value + 17 * value) % 1000003
                    bucket[1] += 1
                self.assertEqual(expected_result(rows),
                                 [(key, *expected[key]) for key in sorted(expected)])

    def test_shared_database_results_match_across_execution_modes(self):
        fingerprints = set()
        for threads in (1, 4):
            for queries in (1, 4):
                with self.subTest(threads=threads, queries=queries):
                    case = run_case(threads=threads, queries=queries, rows=131073)
                    self.assertEqual(case["threads"], threads)
                    self.assertEqual(len(case["results"]), queries)
                    fingerprints.add(case["result_sha256"])
        self.assertEqual(len(fingerprints), 1)

    def test_timeout_cleans_up_child_process(self):
        before = {process.pid for process in multiprocessing.active_children()}
        with self.assertRaisesRegex(TimeoutError, "deadline"):
            run_case(timeout=0.001)
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, before)


if __name__ == "__main__":
    unittest.main()
