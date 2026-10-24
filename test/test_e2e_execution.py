"""Check complete single-pass batches, cache-state handling, and user-visible timing."""

from contextlib import contextmanager
from collections import Counter
from copy import deepcopy
from threading import Lock
import unittest

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
        self.request_count = 0
        self.failed_requests = 0

    def reset(self):
        self.resets += 1
        self.counts.clear()

    def dataset(self):
        return {"update_time": "same"}

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
            misses = self.misses - before
            state.update(metrics={"cache_misses": misses, "cache_hits": 0,
                                  "downloaded_bytes": misses * 100, "range_requests": misses,
                                  "range_seconds": 0.0}, request_count=self.request_count,
                         failed_requests=self.failed_requests, events=[], events_complete=True, errors=[])


def sample_plan():
    return plan.build_plan([{"ticker": "A"}, {"ticker": "B"}],
                           {"price": {"call": "price", "kwargs": {}}})


class TestE2EExecution(unittest.TestCase):
    def test_disk_reuse_runs_one_pass_and_reports_remaining_misses(self):
        class ReusedBackend(FakeBackend):
            def reset(self, *, preserve_disk=False):
                self.preserve_disk = preserve_disk
                super().reset()

        backend = ReusedBackend()
        backend.miss = True
        result = execution.measure_throughput(sample_plan(), backend, "disk_reuse", 4)
        self.assertTrue(backend.preserve_disk)
        self.assertEqual(backend.resets, 1)
        self.assertCountEqual(backend.calls, ["A", "B"])
        self.assertEqual(result["successful_tasks"], 2)
        self.assertEqual(result["cache_misses"], 2)

    def test_unknown_cache_state_or_worker_count_is_rejected(self):
        for state, workers in (("cached", 4), ("cold", 3)):
            with self.subTest(state=state, workers=workers), self.assertRaisesRegex(ValueError, "scenario"):
                execution.measure_throughput(sample_plan(), FakeBackend(), state, workers)

    def test_recovered_transport_errors_do_not_override_successful_api_calls(self):
        for state in ("cold", "disk_reuse"):
            with self.subTest(state=state):
                backend = FakeBackend()
                backend.reset = lambda **kwargs: None
                backend.failed_requests = 3
                result = execution.measure_throughput(sample_plan(), backend, state, 4)
                self.assertEqual(result["status"], "complete")
                self.assertEqual(result["successful_tasks"], 2)
                self.assertEqual(result["failed_tasks"], 0)
                self.assertEqual(result["requests"]["failed_requests"], 3)
                self.assertCountEqual(backend.calls, ["A", "B"])

    def test_product_cache_misses_are_distinct_from_range_request_count(self):
        backend = FakeBackend()
        backend.request_count = 5
        result = execution.measure_throughput(sample_plan(), backend, "cold", 4)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["cache_misses"], 0)
        self.assertEqual(result["requests"]["request_count"], 5)
        self.assertEqual(len(backend.calls), 2)

    def test_prefetch_failure_fails_the_batch_and_keeps_its_evidence(self):
        backend = FakeBackend()
        backend.drain = lambda: (_ for _ in ()).throw(RuntimeError("Expected prefetch failure"))
        backend.miss = True
        with self.assertRaisesRegex(RuntimeError, "prefetch failure") as caught:
            execution.measure_throughput(sample_plan(), backend, "cold", 4)
        evidence = caught.exception.evidence
        self.assertEqual(evidence["requests"]["metrics"]["cache_misses"], 2)
        self.assertEqual(len(evidence["results"]), 2)

    def test_cold_throughput_executes_the_work_once_at_every_worker_count(self):
        for workers in (1, 4, 16, 128):
            with self.subTest(workers=workers):
                backend = FakeBackend()
                result = execution.measure_throughput(sample_plan(), backend, "cold", workers)
                self.assertEqual(backend.resets, 1)
                self.assertCountEqual(backend.calls, ["A", "B"])
                self.assertEqual(result["completed_tasks"], 2)

    def test_errors_are_retained_and_never_counted_as_successes(self):
        backend = FakeBackend()
        backend.fail = "A"
        result = execution.measure_throughput(sample_plan(), backend, "cold", 4)
        self.assertEqual(result["completed_tasks"], 2)
        self.assertEqual(result["successful_tasks"], 1)
        self.assertEqual(result["failed_tasks"], 1)
        self.assertEqual(result["status"], "query_errors")

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

    def test_budget_stop_produces_incomplete_coverage(self):
        result = execution.measure_throughput(sample_plan(), FakeBackend(), "cold", 4, stop=lambda: True)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["completed_tasks"], 0)

    def test_duplicate_or_missing_outcome_is_rejected(self):
        task = next(plan.tasks(sample_plan()))
        row = {"id": task["id"], "status": "ok", "seconds": 1.0,
               "fingerprint": {"sha256": "same"}}
        with self.assertRaisesRegex(ValueError, "completion ledger"):
            execution.validate_ledger(sample_plan(), [row, deepcopy(row)])
