"""Preserve industry calculations while sharing exchange-rate alignment per call."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

from defeatbeta_api.data.ticker import Ticker


VALUATIONS = {
    "industry_ttm_pe": "select_ttm_net_income_by_industry",
    "industry_ps_ratio": "select_ttm_revenue_by_industry",
    "industry_pb_ratio": "select_quarterly_book_value_of_equity_by_industry",
}
PAIRS = {
    "industry_roe": ("select_ttm_roe_by_industry", "_ttm_net_income", "_ttm_avg_equity"),
    "industry_roa": ("select_ttm_roa_by_industry", "_ttm_net_income", "_ttm_avg_assets"),
    "industry_roic": ("select_ttm_roic_by_industry", "_ttm_nopat", "_ttm_avg_invested_capital"),
    "industry_quarterly_gross_margin": ("select_ttm_gross_margin_by_industry", "_ttm_gross_profit", "_ttm_revenue"),
    "industry_quarterly_ebitda_margin": ("select_ttm_ebitda_margin_by_industry", "_ttm_ebitda", "_ttm_revenue"),
    "industry_quarterly_net_margin": ("select_ttm_net_margin_by_industry", "_ttm_net_income", "_ttm_revenue"),
}
METHODS = [*VALUATIONS, *PAIRS, "industry_equity_multiplier", "industry_asset_turnover"]
# Captured from the unchanged calculations before exchange-rate reuse.
SNAPSHOTS = Path(__file__).with_name("fixtures") / "industry_currency.json"


def subject(scenario="normal"):
    """Return deterministic SQL results without constructing a network client."""
    ticker = Ticker.__new__(Ticker)
    ticker.ticker = "AAA"
    ticker.info = Mock(return_value={"industry": "Example"})
    ticker.huggingface_client = SimpleNamespace(get_url_path=lambda name: name)
    currencies = {"AAA": "USD", "BBB": "CNY", "CCC": "CNY", "DDD": "EUR", "SKIP": "JPY"}
    ticker.company_meta = SimpleNamespace(get_financial_currency_map=lambda: currencies.copy())
    dates = pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"])
    index = [7, 2, 9, 4] if scenario == "index" else None
    data = {"report_date": dates}
    for n, symbol in enumerate(["AAA", "BBB", "CCC", "DDD", "DEFAULT"]):
        data[symbol] = [np.nan, 10.005 + n, -3.335 + n, 20.015 + n]
    if scenario == "extreme":
        data["AAA"] = [np.nan, 0.0, np.inf, -np.inf]
        data["CCC"] = [1.0, np.nan, 0.0, -3.335]
    amounts = pd.DataFrame(data, index=index)
    market = amounts.copy()
    for n, symbol in enumerate(list(data)[1:]):
        market[symbol] = [100.0 + n, 200.0 + n, np.nan, 400.0 + n]
    frames = {
        "select_tickers_by_industry": pd.DataFrame({"symbol": [*currencies, "DEFAULT"]}),
        "select_market_cap_by_industry": market,
        **{name: amounts for name in VALUATIONS.values()},
    }
    for name, first, second in PAIRS.values():
        table = {"report_date": dates}
        for symbol in list(data)[1:]:
            table[symbol + first] = amounts[symbol].to_numpy()
            table[symbol + second] = amounts[symbol].to_numpy() * 3.0 + 0.005
        table["SKIP" + first] = [1.0] * 4  # No paired denominator: do not load JPY.
        frames[name] = pd.DataFrame(table, index=index).iloc[::-1]
    ticker.duckdb_client = SimpleNamespace(query=Mock(side_effect=lambda sql: frames[sql].copy(deep=True)))
    fx_dates = pd.to_datetime(["2024-02-01", "2024-02-29", "2024-02-29", "2024-04-01"])
    curves = {
        "CNY=X": pd.DataFrame({"report_date": fx_dates, "close": [7.0, 7.1, 7.2, 7.3]}),
        "EUR=X": pd.DataFrame({"report_date": fx_dates, "close": [0.9, 0.95, 0.96, 0.97]}),
    }
    if scenario == "extreme":
        curves["CNY=X"]["close"] = [np.nan, 0.0, 0.0, np.inf]
    ticker.currency = Mock(side_effect=lambda *, symbol: curves[symbol].copy(deep=True))
    ticker._exchange_rates = Mock(side_effect=lambda symbols: {
        symbol: curves[symbol].copy(deep=True) for symbol in symbols})
    return ticker


def requested_rates(ticker):
    """Count the rate symbols requested, one entry per batched query."""
    return Counter(symbol for call in ticker._exchange_rates.call_args_list for symbol in call.args[0])


def rate_tables(ticker, *currencies):
    return ticker._industry_rate_tables(currencies)


def decode_frame(saved):
    frame = pd.DataFrame(saved["data"], columns=saved["columns"], index=saved["index"])
    for column, dtype in zip(saved["columns"], saved["dtypes"]):
        frame[column] = (pd.to_datetime(frame[column]).astype(dtype) if dtype.startswith("datetime64")
                         else frame[column].astype(dtype))
    return frame


class TestIndustryCurrency(unittest.TestCase):
    def invoke(self, ticker, method):
        with np.errstate(invalid="ignore"), patch(
                "defeatbeta_api.data.ticker.load_sql", side_effect=lambda name, **kw: name):
            return getattr(ticker, method)()

    def test_all_industry_results_match_preoptimization_snapshots_exactly(self):
        snapshots = json.loads(SNAPSHOTS.read_text())
        for scenario, methods in snapshots.items():
            for method, expected in methods.items():
                with self.subTest(scenario=scenario, method=method):
                    actual = self.invoke(subject(scenario), method)
                    assert_frame_equal(actual, decode_frame(expected), check_exact=True)

    def test_each_calculation_loads_its_rates_in_one_query_and_aligns_once(self):
        for method in [*VALUATIONS, *PAIRS]:
            with self.subTest(method=method):
                ticker = subject()
                original = pd.merge_asof
                aligned = Counter()

                def merge(left, right, *args, **kwargs):
                    if "close" in right:
                        aligned[tuple(right["close"].tolist())] += 1
                    return original(left, right, *args, **kwargs)

                with patch("defeatbeta_api.data.ticker.pd.merge_asof", side_effect=merge):
                    self.invoke(ticker, method)
                ticker._exchange_rates.assert_called_once_with(["CNY=X", "EUR=X"])
                ticker.currency.assert_not_called()
                self.assertTrue(all(count == 1 for count in aligned.values()), aligned)

    def test_a_new_call_loads_new_rates_and_keeps_date_axes_separate(self):
        ticker = subject()
        first = self.invoke(ticker, "industry_ps_ratio")
        source = ticker._exchange_rates.side_effect
        ticker._exchange_rates.side_effect = lambda symbols: {
            symbol: frame.assign(close=frame.close * 2) for symbol, frame in source(symbols).items()}
        second = self.invoke(ticker, "industry_ps_ratio")
        self.assertFalse(first.equals(second))
        self.assertEqual(ticker._exchange_rates.call_count, 2)
        self.invoke(ticker, "industry_roa")
        self.assertEqual(ticker._exchange_rates.call_count, 3)

    def test_only_usd_and_missing_currency_do_not_query_rates(self):
        for method in [*VALUATIONS, *PAIRS]:
            with self.subTest(method=method):
                ticker = subject()
                ticker.company_meta.get_financial_currency_map = lambda: {}
                self.invoke(ticker, method)
                ticker._exchange_rates.assert_not_called()
                ticker.currency.assert_not_called()

    def test_concurrent_calculations_keep_their_own_rates(self):
        ticker = subject()
        snapshots = json.loads(SNAPSHOTS.read_text())["normal"]
        with patch("defeatbeta_api.data.ticker.load_sql", side_effect=lambda name, **kw: name):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(lambda name: getattr(ticker, name)(), METHODS))
        for method, actual in zip(METHODS, results):
            assert_frame_equal(actual, decode_frame(snapshots[method]), check_exact=True)
        # Nine direct methods and two composite methods, each with two constituents.
        self.assertEqual(requested_rates(ticker), {"CNY=X": 13, "EUR=X": 13})
        self.assertEqual(ticker._exchange_rates.call_count, 13)

    def test_alignment_preserves_duplicate_dates_and_positional_index(self):
        ticker = subject()
        dates = pd.Series(pd.to_datetime(["2024-01-01", "2024-02-29", "2024-02-29"]),
                          index=[8, 3, 5]).astype("datetime64[us]")
        cache, tables = {}, rate_tables(ticker, "CNY")
        actual = ticker._industry_currency_rates(dates, "CNY", cache, tables)
        assert_series_equal(actual, pd.Series([np.nan, 7.2, 7.2], name="close"), check_exact=True)
        self.assertIs(ticker._industry_currency_rates(dates, "CNY", cache, tables), actual)
        ticker._exchange_rates.assert_called_once_with(["CNY=X"])

    def test_empty_alignment_and_invalid_date_order(self):
        ticker = subject()
        empty = pd.Series([], dtype="datetime64[us]")
        self.assertTrue(ticker._industry_currency_rates(empty, "CNY", {}, rate_tables(ticker, "CNY")).empty)
        unsorted = pd.Series(pd.to_datetime(["2024-03-01", "2024-02-01"])).astype("datetime64[us]")
        with self.assertRaisesRegex(ValueError, "sorted"):
            ticker._industry_currency_rates(unsorted, "USD", {}, {})
        with self.assertRaises(ValueError):
            ticker._industry_currency_rates(pd.Series([pd.NaT], dtype="datetime64[us]"), "USD", {}, {})

    def test_failed_rate_load_fails_the_calculation_and_is_not_cached(self):
        ticker = subject()
        source = ticker._exchange_rates.side_effect
        ticker._exchange_rates.side_effect = RuntimeError("Rate load failed")
        with self.assertRaisesRegex(RuntimeError, "Rate load failed"):
            self.invoke(ticker, "industry_roa")
        ticker._exchange_rates.side_effect = source
        snapshots = json.loads(SNAPSHOTS.read_text())["normal"]
        assert_frame_equal(self.invoke(ticker, "industry_roa"), decode_frame(snapshots["industry_roa"]),
                           check_exact=True)
        self.assertEqual(ticker._exchange_rates.call_count, 2)

    def test_batched_rates_restore_date_order_and_fall_back_on_duplicate_dates(self):
        ticker = Ticker.__new__(Ticker)
        ticker.huggingface_client = SimpleNamespace(get_url_path=lambda name: name)
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]).astype("datetime64[us]")
        frame = pd.DataFrame({"symbol": ["EUR=X", "CNY=X", "EUR=X", "CNY=X", "EUR=X", "JPY=X", "JPY=X"],
                              "report_date": [dates[2], dates[1], dates[0], dates[0], dates[1], dates[0], dates[0]],
                              "close": [0.93, 7.2, 0.91, 7.1, 0.92, 140.0, 141.0]})
        ticker.duckdb_client = SimpleNamespace(query=Mock(return_value=frame))
        single = pd.DataFrame({"symbol": ["JPY=X", "JPY=X"], "report_date": [dates[0], dates[0]],
                               "close": [141.0, 140.0]})
        ticker.currency = Mock(return_value=single)
        with patch("defeatbeta_api.data.ticker.load_sql", side_effect=lambda name, **kw: name):
            rates = ticker._exchange_rates(["CNY=X", "EUR=X", "JPY=X"])
        assert_frame_equal(rates["EUR=X"], pd.DataFrame({"symbol": ["EUR=X"] * 3, "report_date": dates,
                                                         "close": [0.91, 0.92, 0.93]}), check_exact=True)
        self.assertEqual(rates["CNY=X"]["close"].tolist(), [7.1, 7.2])
        # Duplicate dates cannot be ordered from the batch; keep the single-symbol result.
        self.assertIs(rates["JPY=X"], single)
        ticker.currency.assert_called_once_with("JPY=X")
        ticker.duckdb_client.query.assert_called_once()

    def test_batched_rates_match_single_currency_queries(self):
        import tempfile
        import duckdb
        from test.client_stub import bare_client

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "exchange_rate.parquet")
            rows = [("EUR=X", "2024-01-02", 0.91), ("CNY=X", "2024-01-02", 7.1), ("EUR=X", "2024-01-03", 0.92),
                    ("JPY=X", "2024-01-02", 141.0), ("CNY=X", "2024-01-03", 7.2), ("EUR=X", "2024-01-04", 0.93)]
            connection = duckdb.connect()
            try:
                connection.execute(
                    "COPY (SELECT s AS symbol, CAST(d AS DATE) AS report_date, c AS open, c AS close "
                    f"FROM (VALUES {', '.join(map(str, rows))}) t(s, d, c)) TO '{path}' (FORMAT PARQUET)")
                ticker = Ticker.__new__(Ticker)
                ticker.ticker = "AAA"
                ticker.huggingface_client = SimpleNamespace(get_url_path=lambda name: path)
                ticker.duckdb_client = bare_client(connection=connection)
                symbols = ["CNY=X", "EUR=X", "GBP=X"]
                batched = ticker._exchange_rates(symbols)
                self.assertEqual(list(batched), symbols)
                dates = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-05"])).astype("datetime64[us]")
                for symbol in symbols:
                    with self.subTest(symbol=symbol):
                        single = ticker.currency(symbol)
                        if single.empty:
                            # An empty result keeps the schema; DuckDB types an empty string column
                            # as object. Calculations only use the aligned close values.
                            self.assertTrue(batched[symbol].empty)
                            self.assertEqual(list(batched[symbol].columns), list(single.columns))
                        else:
                            assert_frame_equal(batched[symbol], single, check_exact=True)
                        align = lambda frame: pd.merge_asof(pd.DataFrame({"report_date": dates}), frame,
                                                            on="report_date", direction="backward")["close"]
                        assert_series_equal(align(batched[symbol]), align(single), check_exact=True)
                self.assertTrue(batched["GBP=X"].empty)
            finally:
                connection.close()

if __name__ == "__main__":
    unittest.main()
