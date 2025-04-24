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

**Usage**