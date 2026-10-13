"""Check mixed benchmark attribution and result equivalence safeguards."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.workloads.http_pool_mixed import TASKS, QueueSamples, batch_plan, check_fingerprint, distribution, summarize


class TestMixedPoolBenchmark(unittest.TestCase):
    def test_upstream_control_restores_the_adapter_after_failure(self):
        from benchmark.workloads.http_pool_mixed import run
        from defeatbeta_api.client import http_pool

        original = http_pool.coordinate_receives

        def fail(args):
            self.assertIsNot(http_pool.coordinate_receives, original)
            self.assertIsNone(http_pool.coordinate_receives(object()))
            raise ValueError("Controlled benchmark failure")

        with patch("benchmark.workloads.http_pool_mixed._run", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "Controlled benchmark failure"):
                run(SimpleNamespace(receive_mode="upstream"))
        self.assertIs(http_pool.coordinate_receives, original)

    def test_reversed_order_keeps_same_concurrency_reuse_batches_adjacent(self):
        self.assertEqual(batch_plan([32, 64], 2), [(32, 1), (32, 2), (64, 1), (64, 2)])
        self.assertEqual(batch_plan([32, 64], 2, reverse=True), [(64, 1), (64, 2), (32, 1), (32, 2)])

    def test_queue_during_initialization_is_not_reported_as_full_budget(self):
        samples = QueueSamples()
        samples.observe({"configuration": {"max_connections_for_all_origins": 2},
                         "pending_requests": 10, "connections": [
                             {"state": "connecting", "reserved_streams": 1, "effective_stream_limit": 0}]})
        summary = samples.summary()
        self.assertEqual(summary["pending_below_connection_budget"], 1)
        self.assertEqual(summary["pending_while_connecting"], 1)
        self.assertEqual(summary["pending_at_budget_with_all_slots_reserved"], 0)
        self.assertIsNone(summary["full_capacity_example"])

    def test_full_capacity_requires_simultaneous_queue_and_saturated_slots(self):
        samples = QueueSamples()
        state = {"configuration": {"max_connections_for_all_origins": 1},
                 "pending_requests": 3, "connections": [
                     {"state": "busy", "reserved_streams": 4, "effective_stream_limit": 4}]}
        samples.observe(state)
        samples.observe({**state, "pending_requests": 0})
        samples.observe({**state, "connections": [
            {"state": "ready", "reserved_streams": 3, "effective_stream_limit": 4}]})
        summary = samples.summary()
        self.assertEqual(summary["pending_at_budget_with_all_slots_reserved"], 1)
        self.assertEqual(summary["full_capacity_example"]["pending_requests"], 3)

    def test_workload_contains_distinct_balanced_symbol_api_pairs(self):
        self.assertEqual(len(TASKS), 128)
        self.assertEqual(len(set(TASKS)), 128)
        for size in (32, 64, 128):
            for method in ("price", "info", "calendar", "dividends"):
                self.assertEqual(sum(api == method for _, api in TASKS[:size]), size // 4)

    def test_overlapping_worker_and_pool_spans_remain_separate(self):
        timeline = SimpleNamespace(events=[
            {"phase": "cache.worker_queue", "duration_ns": 2_000_000_000},
            {"phase": "transport.pool_wait", "duration_ns": 3_000_000_000},
        ], requests=[
            {"range": "bytes=0-3", "file": "prices.parquet", "origin_host": "cdn.example",
             "body_bytes": 4, "query_id": 1, "start_ns": 0, "headers_received_ns": 4_000_000_000,
             "first_body_delivered_ns": 5_000_000_000, "last_body_delivered_ns": 6_000_000_000},
            {"file": "spec.json", "body_bytes": 90, "query_id": None},
        ], recording_ns=10)
        result = summarize(timeline)
        self.assertEqual(result["worker_queue"]["total_seconds"], 2)
        self.assertEqual(result["pool_acquire"]["total_seconds"], 3)
        self.assertEqual(result["request_until_headers"]["p95_seconds"], 4)
        self.assertEqual(result["body_delivery"]["total_seconds"], 1)
        self.assertEqual(result["range_body_bytes"], 4)
        self.assertEqual(result["unattributed_range_requests"], 0)

    def test_failed_ranges_and_empty_distributions_remain_visible(self):
        timeline = SimpleNamespace(events=[], requests=[
            {"range": "bytes=0-3", "file": "prices.parquet", "origin_host": "cdn.example",
             "body_bytes": 0, "query_id": None, "error_type": "TimeoutError"},
        ], recording_ns=0)
        result = summarize(timeline)
        self.assertEqual(result["files"]["prices.parquet"]["errors"], 1)
        self.assertEqual(result["unattributed_range_requests"], 1)
        self.assertIsNone(result["request_until_headers"]["p95_seconds"])
        self.assertEqual(distribution([])["total_seconds"], 0)

    def test_changed_or_empty_query_results_are_compared(self):
        expected = {}
        check_fingerprint(expected, "PDD", "dividends", {"rows": 0, "sha256": "abc"})
        check_fingerprint(expected, "PDD", "dividends", {"rows": 0, "sha256": "abc"})
        with self.assertRaises(ValueError):
            check_fingerprint(expected, "PDD", "dividends", {"rows": 1, "sha256": "def"})
