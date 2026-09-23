# 000_baseline: Stock Price Cold Query (baseline-multi)

## Environment

| Item | Value |
| --- | --- |
| Date / OS | 2026-09-22 / macOS-26.6.2-arm64-arm-64bit, arm64 |
| CPU / RAM | 10 cores / 16 GiB |
| Python / DuckDB / pandas | 3.11.10 / 1.4.3 / 3.0.1 |
| cache_httpfs / httpfs | cache_httpfs 9c7a709 / httpfs 9c7d349 |
| Threads / memory limit | 4 / 12GB |
| HTTP proxy / keep-alive | http://127.0.0.1:8118 / false |
| Reader | cache_httpfs (on-disk) |
| Dataset | defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet |
| Revision | a46d68650c1f90b7331608350dced8364047b3f7 |
| Samples | AAPL (8,004 rows), KDP (4,622 rows), ZTS (3,429 rows) |
| Cold state | Fresh process and unique empty cache_httpfs directory per trial; no query warmup |

## Run

From the project root (dependencies and extensions already installed):

```bash
.venv/bin/python benchmark/bench.py run --runs 3 --tag baseline-multi --http-proxy "http://127.0.0.1:8118" --timeout 600.0 --revision a46d68650c1f90b7331608350dced8364047b3f7
```

Default: AAPL, KDP, ZTS in round-robin order, 3 trials each. Use `--symbol` for a single stock.

## Result

| Symbol | Rows | Trial 1 (s) | Trial 2 (s) | Trial 3 (s) | Median (s) | Sample std (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AAPL | 8,004 | 19.069100 | 12.618432 | 15.078103 | **15.078103** | 3.255487 |
| KDP | 4,622 | 12.165869 | 12.145379 | 13.124058 | **12.165869** | 0.559220 |
| ZTS | 3,429 | 9.121177 | 8.507444 | 12.126243 | **9.121177** | 1.936612 |

### Timing Breakdown (Median Run, AAPL)

| Phase | Time (s) | % of E2E |
| --- | ---: | ---: |
| Process startup | 0.026 | 0.2% |
| DuckDB init + extension load | 0.357 | 2.4% |
| Data query + materialization | 14.696 | 97.5% |
| **Total (E2E)** | **15.078** | **100%** |

### Cache Footprint

| Symbol | Cache Files | Cache Bytes |
| --- | ---: | ---: |
| AAPL | 3 | 2.65 MB |
| KDP | 3 | 2.65 MB |
| ZTS | 2 | 1.65 MB |

### Result Checksums

| Symbol | SHA256 |
| --- | --- |
| AAPL | `947f24337467c764459d3f78f296dfc4791cea1e3aeab68197a0e9d13a3662a1` |
| KDP | `f09c26da26e795c0dc5e9e281dcd9ec6edc4540c74a4b2028173dd8bbb55e4d2` |
| ZTS | `edcda943aa424bc7e92b86c49d5470d2752cc25d943cc89b885d8bb43ce7108c` |

All 9 trials succeeded; checksums matched across trials for each symbol.
Use these checksums as the pinned baseline for paired experiments.

Raw results: [archive JSON](./000_baseline.json)
