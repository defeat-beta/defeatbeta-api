"""Offline tests for the all-tickers functional harness."""

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import pandas as pd

from benchmark import all_tickers


def raise_in(path, exception):
    """Raise `exception` from code whose file name is `path`."""
    code = compile("def fail(error):\n    raise error\n", str(path), "exec")
    namespace = {}
    exec(code, namespace)
    try:
        namespace["fail"](exception)
    except Exception as exc:
        return exc


class TestSharding(unittest.TestCase):

    def test_shards_cover_every_symbol_once_with_balanced_sizes(self):
        symbols = [f"S{number:05d}" for number in range(10439)]
        shards = [all_tickers.shard(symbols, index, 8) for index in range(8)]
        self.assertEqual(sorted(symbol for part in shards for symbol in part), sorted(symbols))
        self.assertLessEqual(max(map(len, shards)) - min(map(len, shards)), 1)

    def test_shard_does_not_depend_on_input_order(self):
        symbols = ["MSFT", "AAPL", "TSLA", "NVDA", "AMZN"]
        self.assertEqual(all_tickers.shard(symbols, 1, 2), all_tickers.shard(sorted(symbols), 1, 2))

    def test_invalid_shard_is_rejected(self):
        for index, count in ((2, 2), (-1, 2), (0, 0)):
            with self.subTest(index=index, count=count), self.assertRaises(ValueError):
                all_tickers.shard(["AAPL"], index, count)


class TestClassification(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.package = Path(directory.name, "defeatbeta_api")

    def test_value_error_raised_by_the_package_is_a_business_error(self):
        error = raise_in(self.package / "data" / "ticker.py", ValueError("Unknown industry"))
        self.assertEqual(all_tickers.classify(error, self.package), "expected_error")

    def test_value_error_raised_by_a_dependency_is_unexpected(self):
        error = raise_in(Path(self.package.parent, "pandas", "frame.py"), ValueError("bad"))
        self.assertEqual(all_tickers.classify(error, self.package), "unexpected_error")

    def test_other_errors_raised_by_the_package_are_unexpected(self):
        for error in (IndexError("out of bounds"), KeyError("column"), RuntimeError("x")):
            with self.subTest(error=type(error).__name__):
                raised = raise_in(self.package / "data" / "ticker.py", error)
                self.assertEqual(all_tickers.classify(raised, self.package), "unexpected_error")

    def test_raise_site_is_reported_relative_to_the_package(self):
        error = raise_in(self.package / "data" / "ticker.py", ValueError("x"))
        self.assertEqual(all_tickers.raise_site(error, self.package), "defeatbeta_api/data/ticker.py:2")

    def test_package_site_is_the_last_package_frame_before_a_dependency(self):
        dependency = compile("def fail():\n    raise IndexError('out of bounds')\n",
                             str(Path(self.package.parent, "pandas", "indexing.py")), "exec")
        caller = compile("def call(fail):\n    fail()\n", str(self.package / "data" / "ticker.py"), "exec")
        namespace = {}
        exec(dependency, namespace)
        exec(caller, namespace)
        try:
            namespace["call"](namespace["fail"])
        except IndexError as exc:
            error = exc
        self.assertTrue(all_tickers.raise_site(error, self.package).endswith("pandas/indexing.py:2"))
        self.assertEqual(all_tickers.package_site(error, self.package), "defeatbeta_api/data/ticker.py:2")
        outside = raise_in(Path(self.package.parent, "pandas", "frame.py"), ValueError("x"))
        self.assertIsNone(all_tickers.package_site(outside, self.package))


class FakeEarnings:

    def __init__(self, listing):
        self.listing = listing

    def get_transcripts_list(self):
        return self.listing

    def get_transcript(self, fiscal_year, fiscal_quarter):
        return pd.DataFrame({"year": [fiscal_year], "quarter": [fiscal_quarter]})


class FakeNews:

    def get_news_list(self):
        raise IndexError("no news")

    def get_news(self, uuid):
        raise AssertionError("news_body must not run after its listing failed")


class FakeTicker:

    def __init__(self, transcripts):
        self.transcripts = transcripts

    def price(self):
        return pd.DataFrame({"close": [1.0, 2.0]})

    def currency(self, symbol):
        return pd.DataFrame({"symbol": [symbol]})

    def industry_roe(self):
        raise ValueError("Unknown industry for this ticker")

    def earning_call_transcripts(self):
        return FakeEarnings(self.transcripts)

    def news(self):
        return FakeNews()


METHODS = {
    "currency": {"call": "currency", "kwargs": {"symbol": "EUR=X"}},
    "industry_roe": {"call": "industry_roe", "kwargs": {}},
    "news_body": {"call": "news.get_news", "kwargs": {}},
    "news_list": {"call": "news.get_news_list", "kwargs": {}},
    "price": {"call": "price", "kwargs": {}},
    "transcript_body": {"call": "earning_call_transcripts.get_transcript", "kwargs": {}},
    "transcripts_list": {"call": "earning_call_transcripts.get_transcripts_list", "kwargs": {}},
}
PACKAGE = Path(all_tickers.__file__).resolve().parents[1] / "test"


class TestRunTicker(unittest.TestCase):

    def run_ticker(self, transcripts, currency="EUR"):
        return {row["method"]: row for row in all_tickers.run_ticker(
            "TEST", currency, METHODS, lambda symbol: FakeTicker(transcripts), PACKAGE)}

    def test_every_method_gets_one_classified_row(self):
        listing = pd.DataFrame({"fiscal_year": [2024, 2025, 2025], "fiscal_quarter": [4, 1, 2]})
        rows = self.run_ticker(listing)
        self.assertEqual(set(rows), set(METHODS))
        self.assertEqual(rows["price"]["status"], "ok")
        self.assertEqual(rows["price"]["rows"], 2)
        self.assertEqual(rows["industry_roe"]["status"], "expected_error")
        self.assertEqual(rows["news_list"]["status"], "unexpected_error")
        self.assertEqual(rows["news_list"]["error_type"], "IndexError")

    def test_bodies_use_the_latest_listed_record_or_are_not_applicable(self):
        listing = pd.DataFrame({"fiscal_year": [2025, 2024, 2025], "fiscal_quarter": [1, 4, 2]})
        rows = self.run_ticker(listing)
        self.assertEqual(rows["transcript_body"]["kwargs"], {"fiscal_year": 2025, "fiscal_quarter": 2})
        self.assertEqual(rows["transcript_body"]["status"], "ok")
        self.assertEqual(rows["news_body"]["status"], "not_applicable")
        empty = self.run_ticker(pd.DataFrame({"fiscal_year": [], "fiscal_quarter": []}))
        self.assertEqual(empty["transcript_body"]["status"], "not_applicable")

    def test_currency_uses_the_financial_currency_or_a_default(self):
        self.assertEqual(self.run_ticker(pd.DataFrame())["currency"]["kwargs"], {"symbol": "EUR=X"})
        self.assertEqual(self.run_ticker(pd.DataFrame(), "JPY")["currency"]["kwargs"], {"symbol": "JPY=X"})
        self.assertEqual(self.run_ticker(pd.DataFrame(), "USD")["currency"]["kwargs"], {"symbol": "EUR=X"})
        self.assertEqual(self.run_ticker(pd.DataFrame(), None)["currency"]["kwargs"], {"symbol": "EUR=X"})

    def test_ticker_construction_failure_is_one_unexpected_row(self):
        def factory(symbol):
            raise KeyError("catalog")

        rows = all_tickers.run_ticker("TEST", None, METHODS, factory, PACKAGE)
        self.assertEqual([(row["method"], row["status"]) for row in rows], [("__init__", "unexpected_error")])


def fake_work(symbol, currency, options):
    if symbol == "HANG":
        time.sleep(60)
    if symbol == "CRASH":
        os._exit(3)
    return {"dataset_version": "v1", "calls": [{"method": "price", "status": "ok", "currency": currency}]}


class TestRunShard(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.progress = Path(directory.name, "progress.jsonl")

    def lines(self):
        return {line["symbol"]: line for line in map(json.loads, self.progress.read_text().splitlines())}

    def run_shard(self, jobs, **options):
        settings = {"processes": 2, "ticker_timeout": 5, "work": fake_work, "options": {}}
        settings.update(options)
        return all_tickers.run_shard(jobs, self.progress, **settings)

    def test_every_ticker_is_recorded_once(self):
        jobs = [(f"T{number}", "EUR") for number in range(6)]
        summary = self.run_shard(jobs)
        lines = self.lines()
        self.assertEqual(set(lines), {symbol for symbol, _ in jobs})
        self.assertEqual({line["status"] for line in lines.values()}, {"done"})
        self.assertEqual(lines["T0"]["calls"][0]["currency"], "EUR")
        self.assertEqual(summary["done"], 6)

    def test_finished_tickers_are_skipped_when_resumed(self):
        self.progress.write_text(json.dumps({"symbol": "T0", "status": "done", "calls": []}) + "\n")
        summary = self.run_shard([("T0", None), ("T1", None)])
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(len(self.progress.read_text().splitlines()), 2)

    def test_hung_and_crashed_workers_are_replaced(self):
        jobs = [("HANG", None), ("CRASH", None)] + [(f"T{number}", None) for number in range(4)]
        started = time.monotonic()
        summary = self.run_shard(jobs, ticker_timeout=2)
        self.assertLess(time.monotonic() - started, 30)
        lines = self.lines()
        self.assertEqual(lines["HANG"]["status"], "timeout")
        self.assertEqual(lines["CRASH"]["status"], "crashed")
        self.assertEqual({lines[f"T{number}"]["status"] for number in range(4)}, {"done"})
        self.assertEqual((summary["timeout"], summary["crashed"], summary["done"]), (1, 1, 4))

    def test_tickers_after_the_deadline_are_left_for_a_later_run(self):
        summary = self.run_shard([("T0", None), ("T1", None)], stop_after=0)
        self.assertEqual(summary["not_run"], 2)
        self.assertFalse(self.progress.exists() and self.progress.read_text())


if __name__ == "__main__":
    unittest.main()


class TestMethodSelection(unittest.TestCase):

    def test_selected_bodies_bring_their_listing(self):
        selected = all_tickers.select_methods(METHODS, ["transcript_body", "price"])
        self.assertEqual(set(selected), {"transcript_body", "transcripts_list", "price"})

    def test_no_selection_keeps_every_method(self):
        self.assertEqual(all_tickers.select_methods(METHODS, None), METHODS)

    def test_method_missing_from_an_older_version_is_reported(self):
        methods = {**METHODS, "new_method": {"call": "new_method", "kwargs": {}}}
        rows = {row["method"]: row for row in all_tickers.run_ticker(
            "TEST", None, methods, lambda symbol: FakeTicker(pd.DataFrame()), PACKAGE)}
        self.assertEqual(rows["new_method"]["status"], "missing_method")


def line(symbol, status="done", **calls):
    return {"symbol": symbol, "status": status, "seconds": 1.0, "dataset_version": "v1",
            "calls": [{"method": method, "status": state, "error_type": "IndexError",
                       "package_site": "defeatbeta_api/data/ticker.py:10", "error": "boom"}
                      for method, state in calls.items()]}


class TestRecheckAndVerdicts(unittest.TestCase):

    def test_errors_and_failed_tickers_are_rechecked(self):
        lines = [line("A", price="ok", industry_roe="unexpected_error", dcf_data="expected_error"),
                 line("B", price="ok"), line("C", "timeout"), line("D", "crashed")]
        self.assertEqual(all_tickers.recheck_selection(lines),
                         {"A": ["dcf_data", "industry_roe"], "C": None, "D": None})

    def test_verdict_rules(self):
        cases = [
            ("unexpected_error", "ok", "regression"),
            ("expected_error", "ok", "regression"),
            ("unexpected_error", "expected_error", "regression"),
            ("timeout", "ok", "regression"),
            ("unexpected_error", "unexpected_error", "pre_existing"),
            ("crashed", "timeout", "pre_existing"),
            ("expected_error", "expected_error", "business_error"),
            ("expected_error", "unexpected_error", "business_error"),
            ("unexpected_error", "missing_method", "regression"),
            ("expected_error", "missing_method", "business_error"),
            ("unexpected_error", None, "not_rechecked"),
        ]
        for candidate, baseline, verdict in cases:
            with self.subTest(candidate=candidate, baseline=baseline):
                self.assertEqual(all_tickers.verdict(candidate, baseline), verdict)

    def test_comparison_groups_calls_and_sets_the_status(self):
        candidate = [line("A", industry_roe="unexpected_error", price="ok"),
                     line("B", industry_roe="unexpected_error"),
                     line("C", dcf_data="unexpected_error"), line("D", "timeout")]
        baseline = [line("A", industry_roe="unexpected_error"), line("B", industry_roe="unexpected_error"),
                    line("C", dcf_data="ok"), line("D", price="ok")]
        report = all_tickers.compare(candidate, baseline, planned={"A", "B", "C", "D"})
        self.assertEqual(report["status"], "fail")
        groups = {(group["verdict"], group["method"]): group for group in report["groups"]}
        self.assertEqual(groups["pre_existing", "industry_roe"]["tickers"], ["A", "B"])
        self.assertEqual(groups["regression", "dcf_data"]["tickers"], ["C"])
        self.assertEqual(groups["regression", "__ticker__"]["tickers"], ["D"])
        self.assertEqual(report["calls"]["ok"], 1)

    def test_comparison_without_regressions_passes_and_missing_tickers_are_incomplete(self):
        candidate = [line("A", industry_roe="unexpected_error")]
        baseline = [line("A", industry_roe="unexpected_error")]
        self.assertEqual(all_tickers.compare(candidate, baseline, planned={"A"})["status"], "pass")
        self.assertEqual(all_tickers.compare(candidate, baseline, planned={"A", "B"})["status"], "incomplete")
        self.assertEqual(all_tickers.compare(candidate, [], planned={"A"})["status"], "incomplete")

    def test_markdown_lists_regressions_before_pre_existing_errors(self):
        candidate = [line("A", industry_roe="unexpected_error"), line("C", dcf_data="unexpected_error")]
        baseline = [line("A", industry_roe="unexpected_error"), line("C", dcf_data="ok")]
        report = all_tickers.compare(candidate, baseline, planned={"A", "C"})
        text = all_tickers.render(report)
        self.assertIn("Status: fail", text)
        self.assertLess(text.index("## Regressions"), text.index("## Pre-existing errors"))
        self.assertIn("| dcf_data | IndexError | `defeatbeta_api/data/ticker.py:10` | 1 | C |", text)
