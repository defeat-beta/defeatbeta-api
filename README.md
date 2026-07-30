<img src="./doc/logo.webp" height="100" alt="Defeat Beta">

# Defeat Beta API

[![Python version](https://img.shields.io/badge/python-3.11+-blue.svg?style=flat)](https://pypi.org/project/defeatbeta-api/)
[![PyPI version](https://img.shields.io/pypi/v/defeatbeta-api.svg)](https://pypi.org/project/defeatbeta-api/)
[![PyPI downloads](https://img.shields.io/pypi/dm/defeatbeta-api.svg?label=downloads)](https://pypi.org/project/defeatbeta-api/)
[![GitHub stars](https://img.shields.io/github/stars/defeat-beta/defeatbeta-api.svg?style=social)](https://github.com/defeat-beta/defeatbeta-api)
[![License](https://img.shields.io/github/license/defeat-beta/defeatbeta-api)](LICENSE)
[![MCP Toplist](https://mcptoplist.com/badge/glama%2Fdefeat-beta%2Fdefeatbeta-api.svg)](https://mcptoplist.com/server/glama%2Fdefeat-beta%2Fdefeatbeta-api)

**A local-first Python library for querying periodically refreshed financial datasets with DuckDB—without scraping Yahoo Finance at request time.**

Defeat Beta stores research-oriented financial datasets as public Parquet files on
[Hugging Face](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data).
The Python library queries those files with DuckDB and keeps an on-disk block cache
through [`cache_httpfs`](https://duckdb.org/community_extensions/extensions/cache_httpfs.html).
This makes historical and cross-sectional analysis reproducible while avoiding
request-time Yahoo Finance rate limits.

Defeat Beta is designed for research and analysis. It is **not** a real-time market
data feed, an exchange feed, or a source with a service-level agreement.

## Why Defeat Beta?

- **Reproducible snapshots:** every dataset refresh publishes per-file timestamps in
  [`spec.json`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/blob/main/spec.json).
- **Local-first analytics:** use Python, pandas, or DuckDB SQL while remote Parquet
  reads are filtered and cached locally.
- **Research-ready coverage:** prices, statements, valuation metrics, SEC filings,
  earnings call transcripts, news, revenue breakdowns, and Treasury data.
- **Bulk workflows:** query multiple tickers in parallel instead of making one live
  upstream request per symbol.
- **Agent-ready interfaces:** optional [MCP server](mcp/README.md) and
  [financial-analysis skills](skills/README.md).

## Quickstart

Install the package on macOS, Linux, or Windows:

```bash
pip install defeatbeta-api
```

Query historical prices:

```python
from defeatbeta_api.data.ticker import Ticker

aapl = Ticker("AAPL")
prices = aapl.price()

print(prices.tail())
```

The result is a pandas DataFrame:

```text
     symbol report_date    open   close      high       low    volume
7962   AAPL  2026-07-23  329.85  330.12  333.5800  327.8800  48347900
7963   AAPL  2026-07-24  332.78  335.42  336.4100  331.6300  47721600
7964   AAPL  2026-07-27  334.54  336.91  339.5700  334.0200  49604300
7965   AAPL  2026-07-28  340.03  340.08  342.8900  335.6000  51859000
7966   AAPL  2026-07-29  339.69  338.19  344.5699  337.3501  48852885
```

> The output above is an example snapshot. Check
> [`spec.json`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/blob/main/spec.json)
> for the current per-file refresh timestamps.

Try the project without installing anything in
[JupyterLab on Binder](https://mybinder.org/v2/gh/defeat-beta/defeatbeta-api/main?urlpath=lab/tree/notebooks/00_tutorial_info.ipynb).

## What You Can Query

| Area | Examples |
| --- | --- |
| Market data | Historical OHLCV prices, dividends, splits, exchange rates |
| Company data | Profiles, officers, earnings calendars, SEC filing metadata |
| Financials | Income statements, balance sheets, cash flow statements |
| Valuation | EPS, P/E, P/S, P/B, PEG, market cap, WACC |
| Quality and growth | ROE, ROA, ROIC, margins, year-over-year growth |
| Research text | Earnings call transcripts and financial news |
| Business breakdowns | Revenue and operating metrics by segment or geography |
| Macro data | U.S. Treasury yield curves and S&P 500 return history |

See the [usage index](doc/README.md) for the full API and worked examples.

### Financial statements

```python
statement = aapl.quarterly_income_statement()
statement.print_pretty_table()
```

### Earnings call transcripts

```python
transcripts = aapl.earning_call_transcripts()
print(transcripts.get_transcripts_list().tail())
print(transcripts.get_transcript(2026, 2))
```

Transcript text is fetched only when requested. Listing available calls reads metadata
without loading the full transcript payload.

### Multiple tickers

```python
from defeatbeta_api.data.tickers import Tickers

mega_cap = Tickers(["AAPL", "MSFT", "NVDA"], max_workers=3)
prices = mega_cap.price()
gross_margins = mega_cap.quarterly_gross_margin()
```

Methods that return tabular data combine results into one DataFrame with a `symbol`
column. Methods that return complex objects use a `{symbol: object}` dictionary.

## How It Works

```text
Public financial sources
          |
          v
Periodically refreshed Parquet datasets on Hugging Face
          |
          v
DuckDB projection and predicate pushdown over HTTPS
          |
          v
cache_httpfs on-disk block cache
          |
          v
Python objects and pandas DataFrames
```

The refresh pipeline is separate from the Python package. User queries read the
published snapshot instead of scraping upstream sites on demand. DuckDB requests only
the relevant columns and row groups where possible; `cache_httpfs` then reuses downloaded
blocks across queries.

Performance depends heavily on network location, cache state, selected dataset, and
query shape. A first remote read can take tens of seconds, while a repeated in-process
query against cached blocks can complete in milliseconds. See
[Benchmarks](doc/BENCHMARKS.md) for a transparent sample and reproduction steps.

## Defeat Beta and yfinance

The projects solve different problems:

| | Defeat Beta | yfinance |
| --- | --- | --- |
| Primary use | Reproducible bulk research | Convenient access to current Yahoo Finance data |
| Upstream access | Periodically published snapshots | Request-time retrieval |
| Freshness | Delayed; varies by dataset | Generally closer to the current upstream response |
| Rate limits | No Yahoo request per user query | Upstream limits and availability can apply |
| Query engine | DuckDB, Parquet, pandas | Python and pandas |
| Local cache | Shared block cache | Application-dependent |
| Real-time feed | No | No exchange-grade real-time guarantee |

Use yfinance when current upstream responses matter more than reproducibility. Use
Defeat Beta when you need repeatable historical, cross-sectional, or agent-driven
analysis over a published snapshot.

## Data Freshness, Sources, and Limitations

- Dataset refreshes are periodic, not real time. The authoritative refresh record is
  [`spec.json`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/blob/main/spec.json).
- The dataset card documents sources including Yahoo Finance, Nasdaq, the U.S. Treasury,
  SEC EDGAR, StockAnalysis, and YCharts.
- Coverage and update timing differ by table and symbol. Missing, delayed, revised, or
  incorrectly normalized records are possible.
- The project has no affiliation with or endorsement from Yahoo, Nasdaq, the SEC, the
  U.S. Treasury, StockAnalysis, YCharts, or any exchange.
- The Apache-2.0 license covers this repository's source code. It does not grant rights
  to third-party data. Users are responsible for reviewing applicable source terms and
  determining whether their use is permitted.
- The data and derived analytics are for research and educational use and are not
  investment advice. Validate critical results against primary sources.

Read [Data Sources and Limitations](doc/DATA_AND_LIMITATIONS.md) before using the
project in production or redistributing data.

## More Ways to Use It

- [Complete usage index](doc/README.md)
- [Advanced DuckDB and cache configuration](doc/api/Advanced_Usage.md)
- [DCF valuation with editable Excel output](doc/api/DCF_Examples.md)
- [MCP server](mcp/README.md)
- [Financial-analysis skills](skills/README.md)
- [Jupyter notebooks](notebooks)
- [Changelog](CHANGELOG.rst)

## License

The source code in this repository is licensed under the
[Apache License 2.0](LICENSE).
