"""Protect exhaustive coverage, fixed work, cache conditions, and timing boundaries."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import inspect
import unittest

from benchmark.e2e import plan


class SampleTicker:
    def price(self):
        pass

    def currency(self, symbol):
        pass

    def beta(self, period="5y", benchmark="SPY"):
        pass

    def earning_call_transcripts(self):
        pass

    def news(self):
        pass

    def dcf_data(self):
        pass

    def dcf(self):
        pass

    def download_data_performance(self):
        pass


class TestSampledPlan(unittest.TestCase):
    def make_plan(self):
        return plan.build_plan(
            [{"ticker": "B", "financial_currency": "EUR"}, {"ticker": "A"}],
            plan.query_methods(SampleTicker),
            bodies={"A": {"news_body": {"uuid": "article-a"}}},
            dataset={"update_time": "v1", "footer_index": {"US/a.parquet": {"file_size": 100}}})

    def test_all_tickers_and_query_methods_are_in_the_cartesian_product(self):
        workload = self.make_plan()
        tasks = list(plan.tasks(workload))
        self.assertEqual(workload["symbols"], ["A", "B"])
        self.assertEqual(len(tasks), 2 * len(workload["methods"]))
        self.assertEqual(len({task["id"] for task in tasks}), len(tasks))
        self.assertNotIn("dcf", workload["methods"])
        self.assertNotIn("download_data_performance", workload["methods"])
        self.assertIn("dcf_data", workload["methods"])
        self.assertTrue({"transcripts_list", "transcript_body", "news_list", "news_body"}
                        .issubset(workload["methods"]))

    def test_every_concurrency_consumes_the_exact_same_complete_work(self):
        workload = self.make_plan()
        expected = [task["id"] for task in plan.tasks(workload)]
        phases = plan.phases()
        throughput = [phase for phase in phases if phase["kind"] == "throughput"]
        self.assertEqual(len(throughput), 10)
        for state in ("cold", "cached"):
            selected = [phase for phase in throughput if phase["state"] == state]
            self.assertEqual({phase["concurrency"] for phase in selected}, {1, 4, 16, 64, 128})
            for phase in selected:
                with ThreadPoolExecutor(max_workers=phase["concurrency"]) as pool:
                    completed = list(pool.map(lambda task: task["id"], plan.tasks(workload)))
                self.assertEqual(completed, expected)
        self.assertEqual({phase["kind"] for phase in phases}, {"latency", "throughput"})
        self.assertTrue(all(phase["concurrency"] == 1 for phase in phases if phase["kind"] == "latency"))

    def test_parameters_and_missing_bodies_are_frozen_without_dropping_tasks(self):
        workload = self.make_plan()
        tasks = {(task["symbol"], task["method"]): task for task in plan.tasks(workload)}
        self.assertEqual(tasks["A", "news_body"]["kwargs"], {"uuid": "article-a"})
        self.assertEqual(tasks["B", "currency"]["kwargs"], {"symbol": "EUR=X"})
        self.assertIn("not_applicable", tasks["B", "news_body"])
        self.assertEqual(tasks["A", "beta"]["kwargs"], {"period": "5y", "benchmark": "SPY"})

    def test_unhandled_required_parameter_fails_discovery(self):
        class ChangedTicker(SampleTicker):
            def added(self, mandatory):
                pass
        with self.assertRaisesRegex(ValueError, "mandatory"):
            plan.query_methods(ChangedTicker)

    def test_new_query_method_is_automatically_covered(self):
        class ChangedTicker(SampleTicker):
            def added(self):
                pass
        self.assertIn("added", plan.query_methods(ChangedTicker))

    def test_plan_identity_covers_parameters_and_entire_ticker_universe(self):
        workload = self.make_plan()
        plan.validate_plan(workload)
        for field, value in (("symbols", ["A"]), ("bodies", {}), ("cache_capacity_bytes", 1)):
            changed = deepcopy(workload)
            changed[field] = value
            with self.assertRaises(ValueError):
                plan.validate_plan(changed)
        self.assertGreater(workload["cache_capacity_bytes"], 100)

    def test_actual_ticker_has_no_silently_unclassified_public_methods(self):
        from defeatbeta_api.data.ticker import Ticker
        methods = plan.query_methods(Ticker)
        public = {name for name, method in inspect.getmembers(Ticker, callable) if not name.startswith("_")}
        self.assertEqual(set(methods) - set(plan.WRAPPERS),
                         public - set(plan.EXCLUSIONS) - set(plan.WRAPPER_METHODS))

    def test_fixed_sample_is_not_replaced_when_a_symbol_is_missing(self):
        companies = [{"ticker": symbol} for symbol in plan.SAMPLE_SYMBOLS]
        self.assertEqual([row["ticker"] for row in plan.select_sample(companies)], list(plan.SAMPLE_SYMBOLS))
        with self.assertRaisesRegex(ValueError, "missing catalog tickers"):
            plan.select_sample(companies[:-1])

    def test_duplicate_catalog_entries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate catalog ticker"):
            plan.select_sample([{"ticker": "A"}, {"ticker": "A"}])
