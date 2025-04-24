# Defeat-Beta-API

An open-source alternative to Yahoo Finance's market data APIs with higher reliability.

## Introduction

**Key features:**

✅ **Reliable Data**  
Sources market data directly from Hugging Face's [yahoo-finance-data](https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data) dataset, bypassing Yahoo Finance scraping.

✅ **No Rate Limits**  
Hugging Face's infrastructure provides guaranteed access without API throttling or quotas.

✅ **High Performance**  
[DuckDB's OLAP engine](https://duckdb.org/) + [cache_httpfs](https://duckdb.org/community_extensions/extensions/cache_httpfs.html) extension delivers sub-second query latency.

✅ **SQL-Compatible**  
Python-native interface with full SQL support via DuckDB's optimized execution.

## Quickstart

**Installation**

Install `defeat-beta-api` from PYPI using `pip`:

``` {.sourceCode .bash}
$ pip install defeat-beta-api
```

The list of changes can be found in the [Changelog](https://github.com/defeat-beta/defeatbeta-api/blob/main/CHANGELOG.rst)

**Usage**

**1. Get Stock Info**

```python
from data.ticker import Ticker
ticker = Ticker("TSLA")
ticker.info()
```
![example_1.png](doc/img/example_1.png)

**2. Get Stock Officers**
```python
ticker.officers()
```
![example_2.png](doc/img/example_2.png)

**3. Get Stock Calendar**
```python
ticker.calendar()
```
![example_3.png](doc/img/example_3.png)

**4. Get Stock Earnings**
```python
ticker.earnings()
```
![example_4.png](doc/img/example_4.png)

**5. Get Stock Splits**
```python
ticker.splits()
```
![example_5.png](doc/img/example_5.png)

**6. Get Stock Dividends**
```python
ticker.dividends()
```
![example_6.png](doc/img/example_6.png)

**7. Get Stock Revenue Forecast**
```python
ticker.revenue_forecast()
```
![example_7.png](doc/img/example_7.png)

**8. Get Stock Earnings Forecast**
```python
ticker.earnings_forecast()
```
![example_8.png](doc/img/example_8.png)




