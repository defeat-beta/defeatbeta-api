# Defeat Beta API

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

### Installation

Install `defeatbeta-api` from PYPI using `pip`:

``` {.sourceCode .bash}
$ pip install defeatbeta-api
```

The list of changes can be found in the [Changelog](https://github.com/defeat-beta/defeatbeta-api/blob/main/CHANGELOG.rst)

### Usage

**Main Usage:**
```markdown
0. Stock Price
1. Stock Statement
2. Stock Info 
3. Stock Officers 
4. Stock Calendar 
5. Stock Earnings 
6. Stock Splits 
7. Stock Dividends 
8. Stock Revenue Forecast 
9. Stock Earnings Forecast 
10. Stock Summary 
11. Stock TTM EPS
```

**0. Stock Price**
```python
from data.ticker import Ticker
ticker = Ticker("TSLA")
ticker.price()
```
![example_0.png](doc/img/example_0.png)

**1. Stock Statement**

```python
# get quarterly income_statement
statement=ticker.quarterly_income_statement()
print(statement.pretty_table())
```
![example_11.png](doc/img/example_11.png)

```python
# pandas.DataFrame
ticker.quarterly_income_statement().df()
```
![example_12.png](doc/img/example_12.png)


```python
# get annual income_statement
statement=ticker.annual_income_statement()
# get quarterly balance_sheet
statement=ticker.quarterly_balance_sheet()
# get annual balance_sheet
statement=ticker.annual_balance_sheet()
# get quarterly cash_flow
statement=ticker.quarterly_cash_flow()
# get annual cash_flow
statement=ticker.annual_cash_flow()
```

**2. Stock Info**

```python
ticker.info()
```
![example_1.png](doc/img/example_1.png)

**3. Stock Officers**
```python
ticker.officers()
```
![example_2.png](doc/img/example_2.png)

**4. Stock Calendar**
```python
ticker.calendar()
```
![example_3.png](doc/img/example_3.png)

**5. Stock Earnings**
```python
ticker.earnings()
```
![example_4.png](doc/img/example_4.png)

**6. Stock Splits**
```python
ticker.splits()
```
![example_5.png](doc/img/example_5.png)

**7. Stock Dividends**
```python
ticker.dividends()
```
![example_6.png](doc/img/example_6.png)

**8. Stock Revenue Forecast**
```python
ticker.revenue_forecast()
```
![example_7.png](doc/img/example_7.png)

**9. Stock Earnings Forecast**
```python
ticker.earnings_forecast()
```
![example_8.png](doc/img/example_8.png)

**10. Stock Summary**
```python
ticker.summary()
```
![example_13.png](doc/img/example_13.png)

**11. Stock TTM EPS**
```python
ticker.ttm_eps()
```
![example_14.png](doc/img/example_14.png)