# 000: Stock Price Cold Query Baseline

## Environment

| Item | Value |
| --- | --- |
| Date / OS | 2026-09-22 / macOS 26.6.2, arm64 |
| CPU / RAM | 10 cores / 24 GiB |
| Python / DuckDB / pandas | 3.14.6 / 1.5.3 / 3.0.3 |
| cache_httpfs / httpfs | e39e73c / 52afb42 |
| Threads / memory limit | 4 / 19GB |
| HTTP proxy / keep-alive | http://127.0.0.1:8118 / false |
| Dataset | defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet |
| Revision | a46d68650c1f90b7331608350dced8364047b3f7 |
| Samples | AAPL, KDP, ZTS; candidate row groups 0, 184, 367 of 368 (zero-based) |
| Cold state | New process and empty data cache per trial; OS and remote caches uncontrolled |

## Run

From the project root (dependencies and extensions already installed):

```bash
./.venv/bin/python benchmark/bench.py run --runs 3 --tag baseline-multi --http-proxy http://127.0.0.1:8118 --revision a46d68650c1f90b7331608350dced8364047b3f7
```

Default: AAPL, KDP, ZTS in round-robin order, three trials each. Use `--symbol` for a single stock.

## Result

| Symbol | Rows | Trial 1 (s) | Trial 2 (s) | Trial 3 (s) | Median (s) | Sample std (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AAPL | 8,004 | 13.566593 | 15.172548 | 15.983449 | **15.172548** | 1.230030 |
| KDP | 4,622 | 18.165889 | 15.884403 | 18.694262 | **18.165889** | 1.493300 |
| ZTS | 3,429 | 13.175299 | 10.416439 | 17.701867 | **13.175299** | 3.678283 |

Timing includes process startup through full DataFrame materialization. All nine trials succeeded;
checksums matched across trials for each symbol. Baseline only; no optimization applied.

Raw results: [baseline archive](../results/archive/000_baseline.json), including the earlier AAPL-only attempts.
