import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict

import pandas as pd

from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.data.news import News
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
