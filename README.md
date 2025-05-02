# Defeat Beta API

<a target="new" href="https://pypi.python.org/pypi/defeatbeta-api"><img border=0 src="https://img.shields.io/badge/python-3.7+-blue.svg?style=flat" alt="Python version"></a>
<a target="new" href="https://pypi.python.org/pypi/defeatbeta-api"><img border=0 src="https://img.shields.io/pypi/v/defeatbeta-api.svg?maxAge=60%" alt="PyPi version"></a>
<a target="new" href="https://pypi.python.org/pypi/defeatbeta-api"><img border=0 src="https://img.shields.io/pypi/dm/defeatbeta-api.svg?maxAge=2592000&label=installs" alt="PyPi downloads"></a>
<a target="new" href="https://github.com/defeat-beta/defeatbeta-api"><img border=0 src="https://img.shields.io/github/stars/defeat-beta/defeatbeta-api.svg?style=social&label=Star&maxAge=60" alt="Star this repo"></a>

An open-source alternative to Yahoo Finance's market data APIs with higher reliability.

## Introduction

### Key features:

✅ **Reliable Data**  
Sources market data directly from Hugging Face's [yahoo-finance-data](https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data) dataset, bypassing Yahoo scraping.

✅ **No Rate Limits**  
Hugging Face's infrastructure provides guaranteed access without API throttling or quotas.

✅ **High Performance**  
[DuckDB's OLAP engine](https://duckdb.org/) + [cache_httpfs](https://duckdb.org/community_extensions/extensions/cache_httpfs.html) extension delivers sub-second query latency.

✅ **SQL-Compatible**  
Python-native interface with full SQL support via DuckDB's optimized execution.

### How it compares to yfinance:
`defeatbeta-api` is not superior to `yfinance` in every aspect, but its free and efficient features make it ideal for users needing bulk historical data analysis.

**Advantages over yfinance:**

**1. No rate limits:** defeat-beta avoids Yahoo Finance’s real-time rate limit by fetching data periodically (typically once a week) and uploading it to `Hugging Face`.

**2. Efficient data format:** It uses the Parquet format, supporting flexible SQL queries via `DuckDB`.

**3. High-performance caching:** Data is stored remotely on `Hugging Face` but leverages `cache_httpfs` for local disk caching, ensuring excellent performance.

**Disadvantages compared to yfinance:**

**Non-real-time data:** defeat-beta updates data on a periodic basis (typically weekly), so it cannot provide real-time data, unlike `yfinance`.

## Quickstart

### Installation

Install `defeatbeta-api` from [PYPI](https://pypi.org/project/defeatbeta-api/) using `pip`:

``` {.sourceCode .bash}
$ pip install defeatbeta-api
```

The list of changes can be found in the [Changelog](CHANGELOG.rst)

### Usage

Instantiate the `Ticker` class with a company's ticker symbol. For example, to get Tesla, Inc. data:

```python
import defeatbeta_api
from defeatbeta_api.data.ticker import Ticker
ticker = Ticker('TSLA')
```
The following examples demonstrate common API usage patterns (see more examples in [this documentation](doc/Example.md)):

#### Example: Fetching Stock Price Data
```python
ticker.price()
```
```text
>>> ticker.price()
     symbol report_date    open   close    high     low     volume
0      TSLA  2010-06-29    1.27    1.59    1.67    1.17  281494500
1      TSLA  2010-06-30    1.72    1.59    2.03    1.55  257806500
2      TSLA  2010-07-01    1.67    1.46    1.73    1.35  123282000
3      TSLA  2010-07-02    1.53    1.28    1.54    1.25   77097000
4      TSLA  2010-07-06    1.33    1.07    1.33    1.06  103003500
...     ...         ...     ...     ...     ...     ...        ...
3716   TSLA  2025-04-07  223.78  233.29  252.00  214.25  183453800
3717   TSLA  2025-04-08  245.00  221.86  250.44  217.80  171603500
3718   TSLA  2025-04-09  224.69  272.20  274.69  223.88  219433400
3719   TSLA  2025-04-10  260.00  252.40  262.49  239.33  181722600
3720   TSLA  2025-04-11  251.84  252.31  257.74  241.36  128656900

[3721 rows x 7 columns]
```

#### Example: Accessing Financial Statements
```python
statement=ticker.quarterly_income_statement()
print(statement.pretty_table())
```
```text
>>> statement=ticker.quarterly_income_statement()
>>> print(statement.pretty_table())
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
|                         Breakdown                          |    TTM     |  2024-12-31   | 2024-09-30 | 2024-06-30 | 2024-03-31 | 2023-12-31 | 2023-09-30 | 2023-06-30 | 2023-03-31 | 2022-12-31 | 2022-09-30 | 2022-06-30 |
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
| +Total Revenue                                             | 97,690,000 | 25,707,000    | 25,182,000 | 25,500,000 | 21,301,000 | 25,167,000 | 23,350,000 | 24,927,000 | *          | *          | *          | 16,934,000 |
|  Operating Revenue                                         | 97,690,000 | 25,707,000    | 25,182,000 | 25,500,000 | 21,301,000 | 25,167,000 | 23,350,000 | 24,927,000 | *          | *          | *          | 16,934,000 |
| Cost of Revenue                                            | 80,240,000 | 21,528,000    | 20,185,000 | 20,922,000 | 17,605,000 | 20,729,000 | 19,172,000 | 20,394,000 | *          | *          | *          | 12,700,000 |
| Gross Profit                                               | 17,450,000 | 4,179,000     | 4,997,000  | 4,578,000  | 3,696,000  | 4,438,000  | 4,178,000  | 4,533,000  | *          | *          | *          | 4,234,000  |
| +Operating Expense                                         | 9,690,000  | 2,589,000     | 2,225,000  | 2,351,000  | 2,525,000  | 2,374,000  | 2,414,000  | 2,134,000  | *          | *          | *          | 1,628,000  |
|  Selling General and Administrative                        | 5,150,000  | 1,313,000     | 1,186,000  | 1,277,000  | 1,374,000  | 1,280,000  | 1,253,000  | 1,191,000  | *          | *          | *          | 961,000    |
|  Research & Development                                    | 4,540,000  | 1,276,000     | 1,039,000  | 1,074,000  | 1,151,000  | 1,094,000  | 1,161,000  | 943,000    | *          | *          | *          | 667,000    |
| Operating Income                                           | 7,760,000  | 1,590,000     | 2,772,000  | 2,227,000  | 1,171,000  | 2,064,000  | 1,764,000  | 2,399,000  | *          | *          | *          | 2,606,000  |
| +Net Non-Operating Interest Income Expense                 | 1,219,000  | 346,000       | 337,000    | 262,000    | 274,000    | 272,000    | 244,000    | 210,000    | *          | *          | *          | -18,000    |
|  Non-Operating Interest Income                             | 1,569,000  | 442,000       | 429,000    | 348,000    | 350,000    | 333,000    | 282,000    | 238,000    | *          | *          | *          | 26,000     |
|  Non-Operating Interest Expense                            | 350,000    | 96,000        | 92,000     | 86,000     | 76,000     | 61,000     | 38,000     | 28,000     | *          | *          | *          | 44,000     |
| +Other Income Expense                                      | 11,000     | 830,000       | -325,000   | -602,000   | 108,000    | -145,000   | 37,000     | 328,000    | *          | *          | *          | -114,000   |
|  +Special Income Charges                                   | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
|   Restructuring & Mergers Acquisition                      | 684,000    | 7,000         | 55,000     | 622,000    | *          | 0          | 0          | 0          | *          | 34,000     | 0          | 142,000    |
|  Other Non Operating Income Expenses                       | 695,000    | 837,000       | -270,000   | 20,000     | 108,000    | -145,000   | 37,000     | 328,000    | *          | *          | *          | 28,000     |
| Pretax Income                                              | 8,990,000  | 2,766,000     | 2,784,000  | 1,887,000  | 1,553,000  | 2,191,000  | 2,045,000  | 2,937,000  | *          | *          | *          | 2,474,000  |
| Tax Provision                                              | 1,837,000  | 434,000       | 601,000    | 393,000    | 409,000    | -5,752,000 | 167,000    | 323,000    | *          | *          | *          | 205,000    |
| +Net Income Common Stockholders                            | 7,130,000  | 2,314,000     | 2,167,000  | 1,478,000  | 1,171,000  | 7,927,000  | 1,851,000  | 2,703,000  | *          | *          | *          | 2,256,000  |
|  +Net Income(Attributable to Parent Company Shareholders)  | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
|   +Net Income Including Non-Controlling Interests          | 7,153,000  | 2,332,000     | 2,183,000  | 1,494,000  | 1,144,000  | 7,943,000  | 1,878,000  | 2,614,000  | *          | *          | *          | 2,269,000  |
|    Net Income Continuous Operations                        | 7,153,000  | 2,332,000     | 2,183,000  | 1,494,000  | 1,144,000  | 7,943,000  | 1,878,000  | 2,614,000  | *          | *          | *          | 2,269,000  |
|   Minority Interests                                       | -23,000    | 24,000        | -16,000    | -16,000    | -15,000    | -13,000    | -25,000    | 89,000     | *          | *          | *          | -10,000    |
|  Otherunder Preferred Stock Dividend                       | *          | *             | 0          | *          | -42,000    | *          | 2,000      | 0          | -5,000     | *          | 0          | 3,000      |
| Adjustments for Dilutive Securities                        | 0          | *             | *          | *          | *          | 0          | 0          | 0          | *          | 0          | 0          | 0          |
| Diluted NI Available to Com Stockholders                   | 7,130,000  | 2,314,000     | 2,167,000  | 1,478,000  | 1,171,000  | 7,927,000  | 1,851,000  | 2,703,000  | *          | *          | *          | 2,256,000  |
| Basic EPS                                                  | 3.41       | *             | 0.68       | 0.46       | 0.37       | 2.49       | 0.58       | 0.85       | *          | *          | *          | 0.73       |
| Diluted EPS                                                | 3.1        | *             | 0.62       | 0.42       | 0.34       | 2.27       | 0.53       | 0.78       | *          | *          | *          | 0.65       |
| Basic Average Shares                                       | 3,168,250  | *             | 3,198,000  | 3,191,000  | 3,186,000  | 3,181,000  | 3,176,000  | 3,171,000  | *          | *          | *          | 3,111,000  |
| Diluted Average Shares                                     | 3,480,250  | *             | 3,497,000  | 3,481,000  | 3,484,000  | 3,492,000  | 3,493,000  | 3,478,000  | *          | *          | *          | 3,464,000  |
| Total Operating Income as Reported                         | 7,076,000  | 1,583,000     | 2,717,000  | 1,605,000  | 1,171,000  | 2,064,000  | 1,764,000  | 2,399,000  | *          | *          | *          | 2,464,000  |
| Rent Expense Supplemental                                  | 1,003,000  | 242,000       | 247,000    | 245,000    | 269,000    | 296,000    | 301,000    | 338,000    | *          | *          | *          | *          |
| Total Expenses                                             | 89,930,000 | 24,117,000    | 22,410,000 | 23,273,000 | 20,130,000 | 23,103,000 | 21,586,000 | 22,528,000 | *          | *          | *          | 14,328,000 |
| Net Income from Continuing & Discontinued Operation        | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
| Normalized Income                                          | 7,677,200  | 2361901663.05 | 2,209,900  | 1,969,380  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,389,640  |
| Interest Income                                            | 1,569,000  | 442,000       | 429,000    | 348,000    | 350,000    | 333,000    | 282,000    | 238,000    | *          | *          | *          | 26,000     |
| Interest Expense                                           | 350,000    | 96,000        | 92,000     | 86,000     | 76,000     | 61,000     | 38,000     | 28,000     | *          | *          | *          | 44,000     |
| Net Interest Income                                        | 1,219,000  | 346,000       | 337,000    | 262,000    | 274,000    | 272,000    | 244,000    | 210,000    | *          | *          | *          | -18,000    |
| EBIT                                                       | 9,340,000  | 2,862,000     | 2,876,000  | 1,973,000  | 1,629,000  | 2,252,000  | 2,083,000  | 2,965,000  | *          | *          | *          | 2,518,000  |
| EBITDA                                                     | 14,708,000 | 4,358,000     | 4,224,000  | 3,251,000  | 2,875,000  | 3,484,000  | 3,318,000  | 4,119,000  | *          | *          | *          | *          |
| Reconciled Cost of Revenue                                 | 80,240,000 | 21,528,000    | 20,185,000 | 20,922,000 | 17,605,000 | 20,729,000 | 19,172,000 | 20,394,000 | *          | *          | *          | 12,700,000 |
| Reconciled Depreciation                                    | 5,368,000  | 1,496,000     | 1,348,000  | 1,278,000  | 1,246,000  | 1,232,000  | 1,235,000  | 1,154,000  | *          | *          | *          | 922,000    |
| Net Income from Continuing Operation Net Minority Interest | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
| Total Unusual Items Excluding Goodwill                     | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
| Total Unusual Items                                        | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
| Normalized EBITDA                                          | 15,392,000 | 4,365,000     | 4,279,000  | 3,873,000  | 2,875,000  | 3,484,000  | 3,318,000  | 4,119,000  | *          | *          | *          | 3,582,000  |
| Tax Rate for Calcs                                         | 0.2        | 0.16          | 0.22       | 0.21       | 0.26       | 0.21       | 0.08       | 0.11       | *          | *          | *          | 0.08       |
| Tax Effect of Unusual Items                                | -136,800   | -1098336.95   | -12,100    | -130,620   | 0          | 0          | 0          | 0          | *          | *          | *          | -11,360    |
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
```

### Advanced Usage

See [Advanced Usage](doc/Advanced.md) for details.