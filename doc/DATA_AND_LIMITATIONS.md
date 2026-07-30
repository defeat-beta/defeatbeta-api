# Data Sources and Limitations

This document explains what the Defeat Beta Python package does and does not guarantee.
Read it before using the project in production, redistributing data, or making decisions
that require authoritative records.

## Architecture and Responsibility

The Python package queries a separately maintained public dataset:

- Dataset: [defeatbeta/yahoo-finance-data](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data)
- Per-file refresh record: [`spec.json`](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/blob/main/spec.json)
- Dataset license metadata: ODC Attribution License
- Source-code license: Apache License 2.0

The source-code license and dataset license metadata do not override third-party
website, API, content, database, trademark, or redistribution terms. Users are
responsible for reviewing the terms that apply to their use case.

## Documented Upstream Sources

The dataset card identifies sources including:

| Data category | Documented source |
| --- | --- |
| Profiles, statements, prices, actions, transcripts | Yahoo Finance |
| Financial news | Yahoo News |
| Earnings calendar | Nasdaq |
| SEC filing metadata | SEC EDGAR |
| Treasury yields | U.S. Department of the Treasury |
| Revenue and operating breakdowns | StockAnalysis |
| Selected trailing metrics | YCharts |

Refer to the dataset card for table-level source URLs and schemas.

## Freshness

Defeat Beta is not a live feed. Each table is refreshed independently, and timing may
change as upstream availability and the refresh pipeline evolve.

The `files` object in `spec.json` records a timestamp for every published file. The
top-level `update_time` records the latest dataset refresh. Treat these timestamps as
the authoritative freshness metadata instead of assuming a fixed daily or weekly
schedule.

The most recent record inside a table can be older than the file timestamp. For
example, a file can be rebuilt today while the latest valid market session or company
filing is from an earlier date.

## Known Limitations

- Source coverage differs by symbol, exchange, geography, security type, and period.
- Upstream corrections or schema changes can revise historical results.
- Delisted, renamed, merged, newly listed, and multi-class securities may have
  incomplete histories or ticker mapping issues.
- Corporate actions, currencies, fiscal calendars, and restatements can complicate
  comparisons across time or companies.
- News and transcript text may be missing, duplicated, truncated, delayed, or subject
  to separate content rights.
- Computed metrics depend on source definitions, normalization rules, and available
  periods; they may differ from vendor or company-reported figures.
- The public Hugging Face dataset and upstream sources can be unavailable or throttled.
- No uptime, latency, completeness, accuracy, or retention service-level agreement is
  provided.

## Appropriate Use

The project is intended for research, education, prototyping, and reproducible analysis.
It is not an exchange-grade market data service and does not provide investment advice.

For material decisions:

1. Check the relevant per-file timestamp in `spec.json`.
2. Inspect the source and units documented in the dataset card.
3. Validate important values against company filings, exchange data, or another
   authoritative primary source.
4. Review the applicable upstream and dataset terms for your use case.
