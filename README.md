# Defeat-Beta-API

An open-source alternative to Yahoo Finance's market data APIs with higher reliability.

## Introduction

**Key features:**

✅ **Reliable Data Source**  
Pulls market data directly from Hugging Face's [yahoo-finance-data](https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data) dataset - no yahoo-finance scraping.

✅ **No Rate Limits**  
Unlike Yahoo Finance's restrictive official API quotas, Hugging Face provides unfettered access.

✅ **Python-First, SQL-Optimized**  
Python API with DuckDB-backed SQL optimization for Hugging Face datasets - simple and easy to understand.

✅ **High Performance**  
[DuckDB's OLAP engine](https://duckdb.org/) + [cache_httpfs](https://duckdb.org/community_extensions/extensions/cache_httpfs.html) extensions for low-latency analytics.

## Quickstart

**Installation**

**Usage**