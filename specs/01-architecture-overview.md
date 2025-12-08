# 01 - Architecture Overview

> System architecture for the Crypto CEX Data API

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE (ETL)                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │  CEX APIs    │───▶│  Ingestion   │───▶│  Transform   │───▶│  Parquet  │ │
│  │  (Binance,   │    │  Workers     │    │  & Validate  │    │  Storage  │ │
│  │  Coinbase,   │    │              │    │              │    │           │ │
│  │  OKX, Bybit) │    │              │    │              │    │           │ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └─────┬─────┘ │
└────────────────────────────────────────────────────────────────────┼───────┘
                                                                     │
                                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HUGGINGFACE DATASETS                                 │
│  datasets/org/crypto-cex-data/                                              │
│  ├── data/                                                                  │
│  │   ├── ohlcv_daily.parquet                                               │
│  │   ├── ohlcv_hourly.parquet                                              │
│  │   ├── funding_rates.parquet                                             │
│  │   ├── open_interest.parquet                                             │
│  │   ├── liquidations.parquet                                              │
│  │   ├── token_info.parquet                                                │
│  │   └── exchange_info.parquet                                             │
│  └── spec.json  (update_time, version)                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                                                     │
                                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLIENT LIBRARY                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  DuckDB +    │◀───│  SQL         │◀───│  Token       │◀── User Code     │
│  │  cache_httpfs│    │  Templates   │    │  Class       │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. Data Pipeline (ETL)

**Repository**: `defeatbeta-crypto-pipeline/`

| Component | Responsibility |
|-----------|---------------|
| **Ingestion Workers** | Fetch data from CEX REST/WebSocket APIs with rate limiting |
| **Transform Layer** | Normalize data across exchanges, validate quality |
| **Storage Layer** | Write to parquet format with proper schemas |
| **Orchestration** | Schedule jobs, handle failures, backfill history |

### 2. HuggingFace Datasets

**Repository**: `datasets/org/crypto-cex-data`

| Component | Responsibility |
|-----------|---------------|
| **Parquet Files** | Store normalized market data |
| **spec.json** | Track update time, version, available tables |
| **README** | Dataset documentation and usage |

### 3. Client Library

**Repository**: `defeatbeta-crypto-api/`

| Component | Responsibility |
|-----------|---------------|
| **DuckDB Client** | Execute SQL queries with caching |
| **HuggingFace Client** | Resolve dataset URLs, check updates |
| **Token Class** | Main API entry point for users |
| **SQL Templates** | Parameterized queries for data access |
| **Reports** | Generate tearsheets and visualizations |

## Data Flow

### Write Path (Pipeline → HuggingFace)

```
1. Scheduler triggers job (cron)
2. Fetcher pulls data from CEX API
3. Normalizer standardizes schema
4. Validator checks data quality
5. Writer appends to parquet
6. Publisher uploads to HuggingFace
7. spec.json updated with new timestamp
```

### Read Path (Client → User)

```
1. User instantiates Token("BTC")
2. Token calls method (e.g., .ohlcv())
3. HuggingFace client resolves parquet URL
4. SQL template loaded and parameterized
5. DuckDB executes query via cache_httpfs
6. Results returned as pandas DataFrame
```

## Design Principles

### From defeatbeta-api

1. **Singleton Pattern**: Single DuckDB connection shared across queries
2. **SQL Templates**: Parameterized queries in separate `.sql` files
3. **JSON Templates**: Configuration and schemas in `.json` files
4. **Visitor Pattern**: For statement/report generation
5. **Lazy Loading**: Data fetched on-demand, cached locally

### Crypto-Specific Adaptations

1. **Multi-Exchange**: Data normalized across exchanges
2. **Time Granularity**: Support for 1m, 5m, 15m, 1h, 4h, 1d intervals
3. **Derivatives Data**: Funding rates, open interest, liquidations
4. **Real-time Consideration**: Hourly updates for active data

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Data Fetching | `ccxt`, `requests` | Multi-exchange support |
| Data Processing | `pandas`, `pyarrow` | DataFrame operations, parquet I/O |
| Storage | Parquet on HuggingFace | Columnar, compressed, accessible |
| Query Engine | DuckDB + cache_httpfs | OLAP performance, HTTP caching |
| Scheduling | APScheduler / GitHub Actions | Flexible job orchestration |
| Client API | Python package | Easy installation via pip |

## Comparison with defeatbeta-api

| Aspect | defeatbeta-api | crypto-cex-api |
|--------|---------------|----------------|
| Data Source | Yahoo Finance (scraped) | CEX APIs (official) |
| Asset Type | Stocks | Cryptocurrencies |
| Update Frequency | Daily | Hourly/Daily |
| Unique Data | Earnings calls, financials | Funding rates, liquidations |
| Entry Point | `Ticker` class | `Token` class |
| Storage | HuggingFace parquet | HuggingFace parquet |
| Query Engine | DuckDB | DuckDB |

## Security Considerations

1. **API Keys**: Never stored in code, use environment variables
2. **Rate Limits**: Respect exchange limits, implement backoff
3. **Data Validation**: Verify data integrity before publishing
4. **No PII**: Only market data, no user information
