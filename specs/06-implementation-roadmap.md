# 06 - Implementation Roadmap

> Phased delivery plan for the Crypto CEX Data API (Dagster-based)

## Overview

Total estimated timeline: **10-12 weeks**

**Technology Stack:**
- **Orchestration**: Dagster (asset-centric data pipelines)
- **Data Processing**: Pandas, PyArrow, Pydantic
- **HTTP Clients**: httpx (async), tenacity (retries)
- **Storage**: Parquet on HuggingFace
- **Query Engine**: DuckDB + cache_httpfs

```
Phase 1: Dagster Foundation      [Week 1-2]  ████████░░░░░░░░░░░░░░░░
Phase 2: Bronze Layer Assets     [Week 3-4]  ░░░░░░░░████████░░░░░░░░
Phase 3: Silver & Gold Layers    [Week 5-6]  ░░░░░░░░░░░░░░░░████████
Phase 4: Client Library          [Week 7-8]  ░░░░░░░░░░░░░░░░░░░░░░░░
Phase 5: Analytics & Reports     [Week 9-10] ░░░░░░░░░░░░░░░░░░░░░░░░
Phase 6: Production & Scaling    [Week 11+]  ░░░░░░░░░░░░░░░░░░░░░░░░
```

---

## Phase 1: Dagster Foundation (Week 1-2)

**Goal**: Set up Dagster project structure with resources and type definitions.

### Deliverables

- [ ] **P1.1** Project scaffolding
  ```
  defeatbeta-crypto-pipeline/
  ├── pyproject.toml
  ├── crypto_pipeline/
  │   ├── definitions.py      # Dagster entry point
  │   ├── assets/
  │   ├── resources/
  │   ├── types/
  │   └── utils/
  └── tests/
  ```

- [ ] **P1.2** Pydantic type definitions
  - `OHLCVRecord` - validated OHLCV data model
  - `FundingRateRecord` - funding rate model
  - `PipelineConfig` - configuration model
  - Type coercion and validation

- [ ] **P1.3** Dagster resources
  - `BinanceClient` - async HTTP client with rate limiting
  - `ParquetIOManager` - custom I/O for partitioned parquet
  - `HuggingFaceResource` - publishing client

- [ ] **P1.4** Async rate limiter
  - Token bucket implementation
  - Per-exchange rate limits
  - Retry with exponential backoff (tenacity)

### Success Criteria

```python
# Dagster dev server starts successfully
# dagster dev -m crypto_pipeline.definitions

# Resources are injectable
from crypto_pipeline.resources import BinanceClient

client = BinanceClient(requests_per_minute=1200)
# Client can be used in asset functions
```

### Dependencies

```toml
dependencies = [
    "dagster >= 1.7.0",
    "dagster-webserver >= 1.7.0",
    "pydantic >= 2.5.0",
    "httpx >= 0.27.0",
    "tenacity >= 8.2.0",
]
```

---

## Phase 2: Bronze Layer Assets (Week 3-4)

**Goal**: Implement raw data ingestion assets with daily partitioning.

### Deliverables

- [ ] **P2.1** Binance bronze assets
  - `bronze_binance_ohlcv` - daily partitioned OHLCV
  - `bronze_binance_funding` - funding rate history
  - `bronze_binance_oi` - open interest snapshots

- [ ] **P2.2** Partition definitions
  - Daily partitions starting from 2020-01-01
  - Partition key format: YYYY-MM-DD
  - Backfill support

- [ ] **P2.3** Error handling
  - Per-symbol error isolation
  - Partial success handling
  - Retry logic for transient failures

- [ ] **P2.4** Asset metadata
  - Row counts, symbols, fetch timestamps
  - Visible in Dagster UI

### Success Criteria

```python
# Bronze assets materialize successfully
# dagster asset materialize -m crypto_pipeline.definitions \
#   --select bronze_binance_ohlcv --partition 2024-01-01

# Dagster UI shows asset lineage and metadata
# http://localhost:3000/assets
```

### Dependencies

```toml
dependencies = [
    "pandas >= 2.2.0",
    "pyarrow >= 15.0.0",
]
```

---

## Phase 3: Silver & Gold Layers (Week 5-6)

**Goal**: Implement data transformation assets and HuggingFace publishing.

### Deliverables

- [ ] **P3.1** Silver layer assets
  - `silver_ohlcv_normalized` - cleaned, validated OHLCV
  - `silver_ohlcv_aggregated` - cross-exchange aggregation
  - `silver_funding_normalized` - normalized funding rates

- [ ] **P3.2** Data quality checks
  - OHLC relationship validation
  - Duplicate detection and removal
  - Negative value checks
  - Asset freshness checks

- [ ] **P3.3** Gold layer assets
  - `gold_huggingface_ohlcv` - published dataset
  - spec.json generation
  - README generation

- [ ] **P3.4** Dagster schedules
  - Daily ingestion schedule (1 AM UTC)
  - Daily publish schedule (2 AM UTC)
  - Backfill job definition

### Success Criteria

```python
# Full pipeline runs end-to-end
# dagster job execute -m crypto_pipeline.definitions -j daily_ingestion_job

# Data appears on HuggingFace
# curl -I https://huggingface.co/datasets/yourorg/crypto-cex-data/resolve/main/spec.json
```

### Dependencies

```toml
dependencies = [
    "huggingface_hub >= 0.20.0",
]
```

---

## Phase 4: Client Library (Week 7-8)

**Goal**: Build the consumer library that queries HuggingFace datasets.

### Deliverables

- [ ] **P4.1** Client library scaffolding
  ```
  defeatbeta-crypto-api/
  ├── defeatbeta_crypto/
  │   ├── client/
  │   ├── data/
  │   └── utils/
  └── tests/
  ```

- [ ] **P4.2** DuckDB client
  - Singleton pattern (from defeatbeta-api)
  - cache_httpfs configuration
  - Cache invalidation on spec.json change

- [ ] **P4.3** Token class
  - `ohlcv()` - daily/hourly candles
  - `funding_rate()` - perpetual funding
  - `open_interest()` - OI snapshots
  - `info()` - token metadata

- [ ] **P4.4** SQL templates
  - Parameterized query files
  - SQL loader utility

### Success Criteria

```python
from defeatbeta_crypto import Token

btc = Token("BTC")

# Query data from HuggingFace via DuckDB
ohlcv = btc.ohlcv(interval="1d", limit=30)
assert len(ohlcv) <= 30
assert 'close' in ohlcv.columns

funding = btc.funding_rate(limit=10)
assert 'funding_rate' in funding.columns
```

### Dependencies

```toml
dependencies = [
    "duckdb >= 1.4.1",
    "pandas >= 2.2.3",
    "requests >= 2.32.3",
]
```

---

## Phase 5: Analytics & Reports (Week 9-10)

**Goal**: Add computed metrics and reporting capabilities.

### Deliverables

- [ ] **P5.1** Computed metrics
  - `volatility()` - rolling realized volatility
  - `returns()` - period returns (1d, 7d, 30d)
  - `funding_rate_annualized()` - annualized funding
  - `market_cap()` - market capitalization

- [ ] **P5.2** Cross-exchange analysis
  - Price divergence detection
  - Volume distribution charts
  - Arbitrage opportunity finder

- [ ] **P5.3** Tearsheet reports
  - HTML template with charts
  - Matplotlib/Seaborn visualizations
  - Jupyter notebook integration

- [ ] **P5.4** Documentation
  - API reference (Sphinx/MkDocs)
  - Usage examples
  - Jupyter tutorials

### Success Criteria

```python
from defeatbeta_crypto import Token

btc = Token("BTC")
vol = btc.volatility(window=30)
btc.tearsheet(output="btc_report.html")
```

---

## Phase 6: Production & Scaling (Week 11+)

**Goal**: Production deployment and multi-exchange support.

### Deliverables

- [ ] **P6.1** Additional exchange resources
  - `CoinbaseClient` - Coinbase Pro API
  - `OKXClient` - OKX spot + futures
  - `BybitClient` - Bybit derivatives

- [ ] **P6.2** Bronze assets for new exchanges
  - `bronze_coinbase_ohlcv`
  - `bronze_okx_ohlcv`
  - `bronze_bybit_ohlcv`

- [ ] **P6.3** Docker deployment
  - `dagster-webserver` container
  - `dagster-daemon` container
  - Docker Compose configuration

- [ ] **P6.4** Monitoring & alerting
  - Asset freshness sensors
  - Failure notifications (Slack/email)
  - Data quality dashboards

- [ ] **P6.5** Performance optimization
  - Parallel asset materialization
  - Incremental processing
  - Memory optimization

### Success Criteria

```python
# Multi-exchange data available
from defeatbeta_crypto import Token

for exchange in ["binance", "coinbase", "okx"]:
    btc = Token("BTC", exchange=exchange)
    print(f"{exchange}: {btc.ohlcv(limit=1)['close'].iloc[0]}")
```

---

## Risk Mitigation

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Exchange API changes | Medium | High | Abstract resource interface, version pinning |
| Rate limiting | High | Medium | Async rate limiter, exponential backoff |
| Data quality issues | Medium | Medium | Pydantic validation, Dagster asset checks |
| HuggingFace downtime | Low | High | cache_httpfs local caching |
| Dagster learning curve | Medium | Low | Start simple, iterate |

### Dependency Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| DuckDB breaking changes | Low | High | Pin version, test upgrades |
| Dagster breaking changes | Low | Medium | Pin version, follow changelog |
| httpx issues | Low | Low | Fallback to requests |

---

## Milestones

| Milestone | Target Date | Criteria |
|-----------|-------------|----------|
| **M1**: Dagster MVP | Week 2 | Dagster dev server runs, resources work |
| **M2**: Bronze Assets | Week 4 | Daily OHLCV materializes from Binance |
| **M3**: HuggingFace Live | Week 6 | Data published and accessible |
| **M4**: Client Beta | Week 8 | `pip install` works, queries succeed |
| **M5**: v1.0 Release | Week 10 | Full feature set, docs complete |
| **M6**: Multi-Exchange | Week 12 | 4+ exchanges, production-ready |

---

## Resource Requirements

### Infrastructure

| Resource | Cost | Notes |
|----------|------|-------|
| GitHub repository | Free | Code hosting |
| HuggingFace dataset | Free | Data hosting (up to 50GB) |
| GitHub Actions | Free | 2000 min/month |
| Local development | Free | Dagster dev server |

### Production (Optional)

| Resource | Cost | Notes |
|----------|------|-------|
| Cloud VM | ~$20/mo | For dagster-daemon |
| Dagster Cloud | ~$100/mo | Managed Dagster (optional) |

### Development

- 1 developer, full-time equivalent
- Or 2 developers, part-time

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     DAGSTER ORCHESTRATION                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Schedules  │  │   Jobs      │  │   Sensors   │             │
│  │  (daily)    │  │ (backfill)  │  │ (freshness) │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    ASSET GRAPH                           │   │
│  │                                                          │   │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐           │   │
│  │  │ BRONZE   │───▶│ SILVER   │───▶│  GOLD    │           │   │
│  │  │ (raw)    │    │ (clean)  │    │ (publish)│           │   │
│  │  └──────────┘    └──────────┘    └──────────┘           │   │
│  │       ▲                                  │               │   │
│  │       │                                  ▼               │   │
│  │  ┌──────────┐                    ┌──────────────┐       │   │
│  │  │ CEX APIs │                    │  HuggingFace │       │   │
│  │  │ Binance  │                    │   Datasets   │       │   │
│  │  │ Coinbase │                    └──────────────┘       │   │
│  │  └──────────┘                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT LIBRARY                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Token     │──│   DuckDB +   │──│  HuggingFace │          │
│  │    Class     │  │ cache_httpfs │  │   Parquet    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. Create `defeatbeta-crypto-pipeline` repository
2. Set up Dagster project with `dagster project scaffold`
3. Implement Pydantic types (`crypto_pipeline/types/`)
4. Implement `BinanceClient` resource
5. Create first bronze asset: `bronze_binance_ohlcv`

**Start Date**: TBD
**Target v1.0**: TBD + 10 weeks
