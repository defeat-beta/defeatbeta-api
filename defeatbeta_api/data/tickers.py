import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict

import pandas as pd

from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.news import News
from defeatbeta_api.data.statement import Statement
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.data.transcripts import Transcripts


class Tickers:
    """Fetch data for multiple stock tickers in a single call.

    All methods execute requests in parallel using a thread pool. The underlying
    DuckDB client is a process-wide singleton whose cursors are thread-safe for
    concurrent reads, so no extra locking is required.

    Args:
        tickers:     List of ticker symbols, e.g. ``['NVDA', 'GOOGL']``.
        http_proxy:  Optional HTTP proxy URL forwarded to each :class:`Ticker`.
        log_level:   Logging level (default ``logging.INFO``).
        config:      Optional :class:`~defeatbeta_api.client.duckdb_conf.Configuration`
                     forwarded to each :class:`Ticker`.
        max_workers: Maximum number of threads used for parallel fetching.
                     ``None`` (default) lets :class:`~concurrent.futures.ThreadPoolExecutor`
                     choose automatically (typically ``min(32, cpu_count + 4)``).
                     Set to ``1`` to disable parallelism entirely.

    Example::

        from defeatbeta_api.data.tickers import Tickers

        t = Tickers(['NVDA', 'GOOGL'])

        # Combined DataFrame for all tickers
        t.info()

        # Dict keyed by symbol for complex objects
        t.news()                      # -> {'NVDA': News(...), 'GOOGL': News(...)}
        t.earning_call_transcripts()  # -> {'NVDA': Transcripts(...), ...}

        # Limit parallelism
        t = Tickers(['NVDA', 'GOOGL', 'MSFT'], max_workers=2)
    """

    def __init__(
        self,
        tickers: List[str],
        http_proxy: Optional[str] = None,
        log_level: Optional[str] = logging.INFO,
        config: Optional[Configuration] = None,
        max_workers: Optional[int] = None,
    ):
        self.tickers = [t.upper() for t in tickers]
        self.max_workers = max_workers
        self._ticker_map: Dict[str, Ticker] = {
            t: Ticker(t, http_proxy=http_proxy, log_level=log_level, config=config)
            for t in self.tickers
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_parallel(self, method_name: str, **kwargs) -> Dict:
        """Call *method_name* on every ticker in parallel.

        Returns a ``{symbol: result}`` dict preserving insertion order.
        Exceptions raised by individual tickers are re-raised immediately.
        """
        results: Dict = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_symbol = {
                executor.submit(getattr(ticker_obj, method_name), **kwargs): symbol
                for symbol, ticker_obj in self._ticker_map.items()
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                results[symbol] = future.result()
        # Re-sort to original ticker order
        return {t: results[t] for t in self.tickers if t in results}

    def _run_parallel_concat(self, method_name: str, **kwargs) -> pd.DataFrame:
        """Call *method_name* on every ticker in parallel and concatenate the
        resulting DataFrames into a single combined DataFrame."""
        results = self._run_parallel(method_name, **kwargs)
        frames = [df for df in results.values() if df is not None and not df.empty]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    # ------------------------------------------------------------------
    # Category 5 – Info
    # ------------------------------------------------------------------

    def info(self) -> pd.DataFrame:
        """Company profile for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("info")

    def officers(self) -> pd.DataFrame:
        """Company officers for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("officers")

    def sec_filing(self) -> pd.DataFrame:
        """SEC filings for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("sec_filing")

    def news(self) -> Dict[str, News]:
        """Latest news for each ticker.

        Returns:
            ``{'NVDA': News(...), 'GOOGL': News(...), ...}``
        """
        return self._run_parallel("news")

    def earning_call_transcripts(self) -> Dict[str, Transcripts]:
        """Earnings-call transcripts for each ticker.

        Returns:
            ``{'NVDA': Transcripts(...), 'GOOGL': Transcripts(...), ...}``
        """
        return self._run_parallel("earning_call_transcripts")

    # ------------------------------------------------------------------
    # Category 1 – Finance
    # ------------------------------------------------------------------

    def price(self) -> pd.DataFrame:
        """Historical OHLCV prices for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("price")

    def splits(self) -> pd.DataFrame:
        """Stock split events for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("splits")

    def dividends(self) -> pd.DataFrame:
        """Dividend events for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("dividends")

    def calendar(self) -> pd.DataFrame:
        """Earnings calendar for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("calendar")

    def shares(self) -> pd.DataFrame:
        """Shares outstanding for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("shares")

    def beta(self, period: str = "5y", benchmark: str = "SPY") -> pd.DataFrame:
        """Beta relative to a benchmark for all tickers, combined into a single DataFrame.

        Args:
            period:    Time period, e.g. ``'1y'``, ``'3y'``, ``'5y'``.
            benchmark: Benchmark symbol (default ``'SPY'``).
        """
        return self._run_parallel_concat("beta", period=period, benchmark=benchmark)

    def quarterly_income_statement(self) -> Dict[str, Statement]:
        """Quarterly income statement for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("quarterly_income_statement")

    def annual_income_statement(self) -> Dict[str, Statement]:
        """Annual income statement for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("annual_income_statement")

    def quarterly_balance_sheet(self) -> Dict[str, Statement]:
        """Quarterly balance sheet for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("quarterly_balance_sheet")

    def annual_balance_sheet(self) -> Dict[str, Statement]:
        """Annual balance sheet for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("annual_balance_sheet")

    def quarterly_cash_flow(self) -> Dict[str, Statement]:
        """Quarterly cash flow statement for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("quarterly_cash_flow")

    def annual_cash_flow(self) -> Dict[str, Statement]:
        """Annual cash flow statement for each ticker.

        Returns:
            ``{'NVDA': Statement(...), 'GOOGL': Statement(...), ...}``
        """
        return self._run_parallel("annual_cash_flow")

    def ttm_eps(self) -> pd.DataFrame:
        """Trailing-twelve-months EPS for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("ttm_eps")

    def ttm_revenue(self) -> pd.DataFrame:
        """Trailing-twelve-months revenue for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("ttm_revenue")

    def ttm_fcf(self) -> pd.DataFrame:
        """Trailing-twelve-months free cash flow for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("ttm_fcf")

    def ttm_net_income_common_stockholders(self) -> pd.DataFrame:
        """Trailing-twelve-months net income (common stockholders) for all tickers,
        combined into a single DataFrame."""
        return self._run_parallel_concat("ttm_net_income_common_stockholders")

    def revenue_by_segment(self) -> pd.DataFrame:
        """Revenue breakdown by segment for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("revenue_by_segment")

    def revenue_by_geography(self) -> pd.DataFrame:
        """Revenue breakdown by geography for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("revenue_by_geography")

    def revenue_by_product(self) -> pd.DataFrame:
        """Revenue breakdown by product for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("revenue_by_product")

    # ------------------------------------------------------------------
    # Category 2 – Value
    # ------------------------------------------------------------------

    def ttm_pe(self) -> pd.DataFrame:
        """Trailing-twelve-months P/E ratio for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("ttm_pe")

    def market_capitalization(self) -> pd.DataFrame:
        """Historical market capitalization for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("market_capitalization")

    def ps_ratio(self) -> pd.DataFrame:
        """Historical P/S ratio for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("ps_ratio")

    def pb_ratio(self) -> pd.DataFrame:
        """Historical P/B ratio for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("pb_ratio")

    def peg_ratio(self) -> pd.DataFrame:
        """Historical PEG ratio for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("peg_ratio")

    def roe(self) -> pd.DataFrame:
        """Historical return on equity for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("roe")

    def roa(self) -> pd.DataFrame:
        """Historical return on assets for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("roa")

    def roic(self) -> pd.DataFrame:
        """Historical return on invested capital for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("roic")

    def equity_multiplier(self) -> pd.DataFrame:
        """Historical equity multiplier for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("equity_multiplier")

    def asset_turnover(self) -> pd.DataFrame:
        """Historical asset turnover for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("asset_turnover")

    def wacc(self) -> pd.DataFrame:
        """Historical WACC for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("wacc")

    # ------------------------------------------------------------------
    # Category 3 – Growth
    # ------------------------------------------------------------------

    def quarterly_revenue_yoy_growth(self) -> pd.DataFrame:
        """Quarterly revenue YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_revenue_yoy_growth")

    def annual_revenue_yoy_growth(self) -> pd.DataFrame:
        """Annual revenue YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("annual_revenue_yoy_growth")

    def quarterly_operating_income_yoy_growth(self) -> pd.DataFrame:
        """Quarterly operating income YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_operating_income_yoy_growth")

    def annual_operating_income_yoy_growth(self) -> pd.DataFrame:
        """Annual operating income YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("annual_operating_income_yoy_growth")

    def quarterly_ebitda_yoy_growth(self) -> pd.DataFrame:
        """Quarterly EBITDA YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_ebitda_yoy_growth")

    def annual_ebitda_yoy_growth(self) -> pd.DataFrame:
        """Annual EBITDA YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("annual_ebitda_yoy_growth")

    def quarterly_net_income_yoy_growth(self) -> pd.DataFrame:
        """Quarterly net income YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_net_income_yoy_growth")

    def annual_net_income_yoy_growth(self) -> pd.DataFrame:
        """Annual net income YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("annual_net_income_yoy_growth")

    def quarterly_fcf_yoy_growth(self) -> pd.DataFrame:
        """Quarterly free cash flow YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_fcf_yoy_growth")

    def annual_fcf_yoy_growth(self) -> pd.DataFrame:
        """Annual free cash flow YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("annual_fcf_yoy_growth")

    def quarterly_eps_yoy_growth(self) -> pd.DataFrame:
        """Quarterly EPS YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_eps_yoy_growth")

    def quarterly_ttm_eps_yoy_growth(self) -> pd.DataFrame:
        """Quarterly TTM EPS YoY growth for all tickers, combined into a single DataFrame."""
        return self._run_parallel_concat("quarterly_ttm_eps_yoy_growth")
