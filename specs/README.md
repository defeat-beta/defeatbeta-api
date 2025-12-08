# Crypto CEX Data API - Specifications

> Specs-Driven Development Documentation for building a cryptocurrency market data library with CEX (Centralized Exchange) support, modeled after [defeatbeta-api](../README.md).

## Overview

This project aims to replicate the architecture and patterns of `defeatbeta-api` (a Yahoo Finance alternative) for the cryptocurrency market, starting with Centralized Exchange (CEX) data.

## Specifications Index

| Document | Description | Status |
|----------|-------------|--------|
| [01 - Architecture Overview](./01-architecture-overview.md) | System architecture, components, data flow | Draft |
| [02 - Data Pipeline](./02-data-pipeline.md) | **Dagster-based** batch pipelines (Bronze/Silver/Gold) | **Updated** |
| [03 - HuggingFace Publishing](./03-huggingface-publishing.md) | Dataset publishing workflow | Draft |
| [04 - Client Library](./04-client-library.md) | Consumer library design and API | Draft |
| [05 - Data Schemas](./05-data-schemas.md) | Parquet schemas, SQL templates | Draft |
| [06 - Implementation Roadmap](./06-implementation-roadmap.md) | **Dagster-based** phased delivery plan | **Updated** |

## Quick Links

- **Reference Implementation**: [defeatbeta-api](https://github.com/defeat-beta/defeatbeta-api)
- **Target Dataset**: HuggingFace Datasets (TBD)
- **Primary Exchanges**: Binance, Coinbase, OKX, Bybit

## Project Goals

1. **High-Performance Data Access**: DuckDB + cache_httpfs for sub-second queries
2. **Reliable Data Source**: Pre-processed parquet files on HuggingFace (no rate limits)
3. **Crypto-Native Metrics**: Funding rates, open interest, liquidations, perpetuals
4. **Multi-Exchange Support**: Normalized data across major CEXs
5. **Familiar API**: Similar patterns to defeatbeta-api for easy adoption

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Orchestration** | Dagster | Asset-centric batch pipelines |
| **Data Models** | Pydantic | Type-safe validation |
| **HTTP Client** | httpx + tenacity | Async requests with retries |
| **Storage** | PyArrow/Parquet | Columnar data format |
| **Publishing** | HuggingFace Hub | Dataset hosting |
| **Query Engine** | DuckDB + cache_httpfs | OLAP queries over HTTP |
| **Client API** | Python package | User-facing library |

## Architecture Summary

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CEX APIs      │────▶│  Data Pipeline  │────▶│   HuggingFace   │
│  (Binance,etc)  │     │  (ETL Jobs)     │     │   Datasets      │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   User Code     │◀────│  Client Library │
                        │                 │     │  (DuckDB+httpfs)│
                        └─────────────────┘     └─────────────────┘
```

## Getting Started

1. Read [Architecture Overview](./01-architecture-overview.md) for system understanding
2. Review [Data Schemas](./05-data-schemas.md) for data structures
3. Check [Implementation Roadmap](./06-implementation-roadmap.md) for development phases

## Contributing

When adding or modifying specs:
1. Update this index if adding new documents
2. Mark document status (Draft/Review/Approved)
3. Include code examples where applicable
4. Reference the original defeatbeta-api patterns being adapted
