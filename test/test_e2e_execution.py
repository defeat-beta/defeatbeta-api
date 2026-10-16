"""Check complete work, local-cache validity, and user-visible timing."""

from contextlib import contextmanager
from collections import Counter
from copy import deepcopy
from threading import Barrier, Lock, get_ident
import unittest
from unittest.mock import patch

from benchmark.e2e import execution, plan


class FakeTicker:
    def __init__(self, symbol, backend):
        self.symbol, self.backend = symbol, backend

    def price(self):
        with self.backend.guard:
            self.backend.calls.append(self.symbol)
            self.backend.counts[self.symbol] += 1
            if (self.backend.miss or self.backend.counts[self.symbol]
                    in self.backend.miss_on_calls.get(self.symbol, ())):
                self.backend.misses += 1
            if self.backend.on_call:
                self.backend.on_call()
        if self.backend.fail == self.symbol:
            raise ValueError("Expected query failure")
        return {"symbol": self.symbol, "value": 1}


class FakeBackend:
    def __init__(self):
        self.calls, self.resets, self.misses = [], 0, 0
        self.miss, self.fail = False, None
        self.counts, self.miss_on_calls = Counter(), {}
        self.guard, self.on_call = Lock(), None

    def reset(self):
        self.resets += 1
        self.counts.clear()

    def ticker(self, symbol):
        return FakeTicker(symbol, self)

    def drain(self):
        return {"errors": 0}

    @contextmanager
    def probe(self):
        before = self.misses
        state = {}
        try:
            yield state
        finally:
            state["misses"] = self.misses - before


def sample_plan():
    return plan.build_plan([{"ticker": "A"}, {"ticker": "B"}],
                           {"price": {"call": "price", "kwargs": {}}})


class TestE2EExecution(unittest.TestCase):
    def test_cached_latency_waits_for_zero_requests_before_measurement(self):
        backend = FakeBackend()
        backend.miss_on_calls = {symbol: {1, 2} for symbol in ("A", "B")}
        result = execution.measure_latency(sample_plan(), backend, "cached")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(backend.calls, ["A"] * 4 + ["B"] * 4)
        for row in result["results"]:
            preparation = row["cache_preparation"]
            self.assertEqual(preparation["status"], "ready")
            self.assertEqual([p["cache_misses"] for p in preparation["passes"]], [1, 1, 0])
            self.assertEqual(row["cache_misses"], 0)

    def test_cached_throughput_replays_the_complete_work_until_ready(self):
        backend = FakeBackend()
        backend.miss_on_calls = {symbol: {1, 2} for symbol in ("A", "B")}
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(backend.calls), 8)
        preparation = result["cache_preparation"]
        self.assertEqual(preparation["concurrency"], 4)
        expected = {task["id"] for task in plan.tasks(sample_plan())}
        self.assertEqual([p["cache_misses"] for p in preparation["passes"]], [2, 2, 0])
        for attempt in preparation["passes"]:
            self.assertEqual(set(attempt["task_ids"]), expected)
        self.assertEqual(result["completed_tasks"], 2)

    def test_preparation_uses_the_requested_concurrency(self):
        backend = FakeBackend()
        barrier, threads = Barrier(2), set()

        class ConcurrentTicker(FakeTicker):
            def price(self):
                with backend.guard:
                    threads.add(get_ident())
                barrier.wait(timeout=5)
                return super().price()

        backend.ticker = lambda symbol: ConcurrentTicker(symbol, backend)
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["status"], "complete")
        self.assertGreaterEqual(len(threads), 2)

    def test_nonconvergent_preparation_is_bounded_and_never_measured(self):
        backend = FakeBackend()
        backend.miss = True
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["completed_tasks"], 0)
        preparation = result["cache_preparation"]
        self.assertEqual(preparation["status"], "not_ready")
        self.assertEqual(len(preparation["passes"]), preparation["max_passes"])
        self.assertEqual(len(backend.calls), 2 * preparation["max_passes"])

    def test_miss_in_formal_measurement_is_not_retried_or_discarded(self):
        backend = FakeBackend()
        backend.miss_on_calls = {"A": {2}}
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["cache_preparation"]["status"], "ready")
        self.assertEqual(result["cache_misses"], 1)
        self.assertEqual(Counter(backend.calls), {"A": 2, "B": 2})

    def test_batch_timing_excludes_all_preparation_passes(self):
        backend = FakeBackend()
        backend.miss_on_calls = {symbol: {1, 2} for symbol in ("A", "B")}
        clock = [0.0]
        backend.on_call = lambda: clock.__setitem__(0, clock[0] + 1)
        with patch.object(execution.time, "perf_counter", side_effect=lambda: clock[0]):
            result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["preparation_seconds"], 6)
        self.assertEqual(result["wall_seconds"], 2)

    def test_all_pairs_are_warmed_before_cached_throughput(self):
        backend = FakeBackend()
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertCountEqual(backend.calls[:2], ["A", "B"])
        self.assertCountEqual(backend.calls[2:], ["A", "B"])
        self.assertEqual(result["expected_tasks"], 2)
        self.assertEqual(result["completed_tasks"], 2)
        self.assertEqual(result["cache_misses"], 0)
        self.assertEqual(result["status"], "complete")

    def test_cold_throughput_does_not_preexecute_the_work(self):
        backend = FakeBackend()
        result = execution.measure_throughput(sample_plan(), backend, "cold", 128)
        self.assertCountEqual(backend.calls, ["A", "B"])
        self.assertEqual(result["completed_tasks"], 2)

    def test_cached_miss_invalidates_even_a_successful_query(self):
        backend = FakeBackend()
        backend.miss_on_calls = {"A": {2}, "B": {2}}
        result = execution.measure_throughput(sample_plan(), backend, "cached", 1)
        self.assertEqual(result["failed_tasks"], 0)
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["cache_misses"], 2)

    def test_nonconvergent_latency_preserves_each_failed_task(self):
        backend = FakeBackend()
        backend.miss = True
        result = execution.measure_latency(sample_plan(), backend, "cached")
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["completed_tasks"], 2)
        self.assertEqual(result["successful_tasks"], 0)
        self.assertEqual(result["failed_tasks"], 2)
        for row in result["results"]:
            self.assertIsNone(row["seconds"])
            self.assertEqual(row["error_type"], "CacheNotReady")
            self.assertEqual(row["stage"], "cache_preparation")
            self.assertEqual(row["cache_preparation"]["status"], "not_ready")

    def test_latency_measurement_miss_is_not_retried(self):
        backend = FakeBackend()
        backend.miss_on_calls = {"A": {2}}
        result = execution.measure_latency(sample_plan(), backend, "cached")
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["cache_misses"], 1)
        self.assertEqual(backend.calls, ["A", "A", "B", "B"])

    def test_budget_stop_during_preparation_is_not_ready_or_measured(self):
        backend = FakeBackend()
        backend.miss = True
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4,
                                              stop=lambda: len(backend.calls) >= 2)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["stage"], "cache_preparation")
        self.assertEqual(result["completed_tasks"], 0)
        self.assertEqual(len(backend.calls), 2)

    def test_prefetch_failure_cannot_produce_a_ready_cache(self):
        backend = FakeBackend()
        backend.drain = lambda: (_ for _ in ()).throw(RuntimeError("Expected prefetch failure"))
        with self.assertRaisesRegex(RuntimeError, "prefetch failure"):
            execution.measure_throughput(sample_plan(), backend, "cached", 4)

    def test_latency_resets_cache_before_every_individual_task(self):
        for state in ("cold", "cached"):
            backend = FakeBackend()
            result = execution.measure_latency(sample_plan(), backend, state)
            self.assertEqual(backend.resets, 2)
            self.assertEqual(len(backend.calls), 2 if state == "cold" else 4)
            self.assertEqual(result["completed_tasks"], 2)

    def test_errors_are_retained_and_never_counted_as_successes(self):
        backend = FakeBackend()
        backend.fail = "A"
        result = execution.measure_throughput(sample_plan(), backend, "cold", 4)
        self.assertEqual(result["completed_tasks"], 2)
        self.assertEqual(result["successful_tasks"], 1)
        self.assertEqual(result["failed_tasks"], 1)
        self.assertEqual(result["status"], "query_errors")
        self.assertTrue(any(row["error_type"] == "ValueError" for row in result["results"] if row["status"] == "error"))

    def test_missing_body_remains_in_the_completion_ledger(self):
        workload = sample_plan()
        workload["methods"] = {"news_body": {"call": "news.get_news", "kwargs": {}}}
        workload["sha256"] = plan.checksum({k: v for k, v in workload.items() if k != "sha256"})
        result = execution.measure_throughput(workload, FakeBackend(), "cold", 4)
        self.assertEqual(result["not_applicable_tasks"], 2)
        self.assertEqual(result["successful_tasks"], 0)
        self.assertEqual(result["completed_tasks"], 2)

    def test_timer_includes_materialization_and_excludes_hashing(self):
        events = []

        class Deferred:
            def df(self):
                events.append("materialize")
                return {"value": 1}

        class Ticker:
            def price(self):
                events.append("call")
                return Deferred()

        def clock():
            events.append("clock")
            return len(events)

        task = next(plan.tasks(sample_plan()))
        result = execution.call(Ticker(), task, clock=clock)
        self.assertEqual(events, ["clock", "call", "materialize", "clock"])
        self.assertIn("value", result)
        self.assertNotIn("fingerprint", result)

    def test_task_failure_during_warmup_is_not_hidden(self):
        backend = FakeBackend()
        backend.fail = "A"
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(result["status"], "warmup_errors")
        self.assertEqual(result["completed_tasks"], 0)
        self.assertEqual(backend.calls, ["A", "B"])

    def test_budget_stop_produces_incomplete_coverage(self):
        result = execution.measure_latency(sample_plan(), FakeBackend(), "cold", stop=lambda: True)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["completed_tasks"], 0)

    def test_duplicate_or_missing_outcome_is_rejected(self):
        task = next(plan.tasks(sample_plan()))
        row = {"id": task["id"], "status": "ok", "seconds": 1.0,
               "fingerprint": {"sha256": "same"}}
        with self.assertRaisesRegex(ValueError, "completion ledger"):
            execution.validate_ledger(sample_plan(), [row, deepcopy(row)])
