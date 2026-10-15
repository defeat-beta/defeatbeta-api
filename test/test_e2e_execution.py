"""Check complete work, local-cache validity, and user-visible timing."""

from contextlib import contextmanager
from copy import deepcopy
import unittest

from benchmark.e2e import execution, plan


class FakeTicker:
    def __init__(self, symbol, backend):
        self.symbol, self.backend = symbol, backend

    def price(self):
        self.backend.calls.append(self.symbol)
        if self.backend.miss:
            self.backend.misses += 1
        if self.backend.fail == self.symbol:
            raise ValueError("Expected query failure")
        return {"symbol": self.symbol, "value": 1}


class FakeBackend:
    def __init__(self):
        self.calls, self.resets, self.misses = [], 0, 0
        self.miss, self.fail = False, None

    def reset(self):
        self.resets += 1

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
    def test_all_pairs_are_warmed_before_cached_throughput(self):
        backend = FakeBackend()
        result = execution.measure_throughput(sample_plan(), backend, "cached", 4)
        self.assertEqual(backend.calls[:2], ["A", "B"])
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
        backend.miss = True
        result = execution.measure_throughput(sample_plan(), backend, "cached", 1)
        self.assertEqual(result["failed_tasks"], 0)
        self.assertEqual(result["status"], "invalid_cache")
        self.assertEqual(result["cache_misses"], 2)

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
