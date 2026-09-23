# 001_resolve_once_cdn: Stock Price Cold Query Comparison

## Environment

| Item | Value |
| --- | --- |
| Run dates | baseline 2026-09-23 / candidate 2026-09-23 |
| OS / machine | macOS-26.6.2-arm64-arm-64bit, arm64 |
| CPU / RAM | 10 cores / 16 GiB |
| Python / DuckDB / pandas | 3.11.10 / 1.5.3 / 3.0.1 |
| cache_httpfs / httpfs | cache_httpfs e39e73c / httpfs 52afb42 |
| Threads / memory limit | 4 / 12GB |
| HTTP proxy / keep-alive | http://127.0.0.1:8118 / true |
| Baseline reader | cache_httpfs via pinned Hugging Face URL |
| Candidate reader | cache_httpfs via signed CDN URL (resolve-once; exact file list) |
| Dataset | defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet |
| Revision | a46d68650c1f90b7331608350dced8364047b3f7 |
| Symbols | AAPL, KDP, ZTS |
| Cold state | Fresh process and unique empty cache_httpfs directory per trial; no query warmup |
| Declared setting differences | `resolve_direct`: false → true |

## Reproduce

From the project root (dependencies and extensions already installed):

Baseline:

```bash
.venv/bin/python benchmark/bench.py run --runs 3 --tag h5_cache_baseline --http-proxy "http://127.0.0.1:8118" --keep-alive --timeout 120.0 --revision a46d68650c1f90b7331608350dced8364047b3f7
```

Candidate:

```bash
.venv/bin/python benchmark/bench.py run --runs 3 --tag h5_resolve_cache --http-proxy "http://127.0.0.1:8118" --keep-alive --resolve-direct --timeout 120.0 --revision a46d68650c1f90b7331608350dced8364047b3f7
```

## Result

| Symbol | Rows | Baseline trials (s) | Candidate trials (s) | Baseline median | Candidate median | Change |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| AAPL | 8,004 | 12.055770, 11.775662, 13.123806 | 8.662071, 17.729711, 8.121322 | 12.055770 | **8.662071** | -28.1% |
| KDP | 4,622 | 11.702303, 15.380871, 11.458069 | 9.820398, 21.962782, 9.819367 | 11.702303 | **9.820398** | -16.1% |
| ZTS | 3,429 | 10.458619, 10.442542, 11.475369 | 7.528044, 47.975588, 9.712032 | 10.458619 | **9.712032** | -7.1% |

### Timing Breakdown (Median Run, AAPL)

| Phase | Baseline (s) | Candidate (s) |
| --- | ---: | ---: |
| Process startup | 0.023 | 0.030 |
| DuckDB init + extension load | 0.288 | 0.305 |
| URL resolve | 0.000 | 0.884 |
| Data query + materialization | 11.744 | 7.443 |
| **Total (E2E)** | **12.056** | **8.662** |

### Cache Footprint

| Symbol | Baseline files / bytes | Candidate files / bytes |
| --- | ---: | ---: |
| AAPL | 3 / 2.65 MB | 3 / 2.65 MB |
| KDP | 3 / 2.65 MB | 3 / 2.65 MB |
| ZTS | 2 / 1.65 MB | 2 / 1.65 MB |

### Result Checksums

| Symbol | Rows | SHA256 |
| --- | ---: | --- |
| AAPL | 8,004 | `947f24337467c764459d3f78f296dfc4791cea1e3aeab68197a0e9d13a3662a1` |
| KDP | 4,622 | `f09c26da26e795c0dc5e9e281dcd9ec6edc4540c74a4b2028173dd8bbb55e4d2` |
| ZTS | 3,429 | `edcda943aa424bc7e92b86c49d5470d2752cc25d943cc89b885d8bb43ce7108c` |

All 18 baseline and candidate trials succeeded. Result hashes match
for every symbol.

## Cache-Key Limitation

The candidate keeps `cache_httpfs`, but the extension keys cached blocks by the
complete signed URL. Observed Hugging Face URLs were valid for approximately
60 minutes, while the production client uses a conservative 30-minute resolve
TTL. Blocks are reused while that exact URL remains active and are not
addressable after a process restart or signature change. Old blocks remain on
disk until normal invalidation or eviction.

## Interpretation

This is an isolated cold-data-cache benchmark, not a machine-cold benchmark.
OS code pages, DNS, proxy behavior, and remote CDN caches remain uncontrolled.
Treat the medians as directional evidence rather than a latency SLA.

Raw paired results: [archive JSON](./001_resolve_once_cdn.json)
