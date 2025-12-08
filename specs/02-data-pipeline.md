# 02 - Data Pipeline

> Modern Python batch pipeline with Dagster orchestration

## Design Philosophy

This pipeline follows modern data engineering principles:

1. **Asset-Centric**: Data assets (parquet files) are first-class citizens, not just pipeline outputs
2. **Declarative**: Define *what* data should exist, not *how* to build it
3. **Incremental**: Process only new/changed data when possible
4. **Type-Safe**: Pydantic models and type hints throughout
5. **Observable**: Built-in lineage, logging, and monitoring
6. **Testable**: Every component is unit-testable in isolation
7. **Pure Python**: No YAML configs for pipeline logic, everything is code

## Technology Choice: Dagster

| Framework | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **Dagster** | Asset-centric, type-safe, great DX, built-in scheduling | Learning curve | **Selected** |
| Prefect | Easy to use, good UI | Flow-centric, less data-focused | Runner-up |
| Airflow | Mature, widely adopted | Task-centric, complex setup | Too heavy |
| dlt | Lightweight, ELT focused | Limited orchestration | Too simple |

## Pipeline Repository Structure

```
defeatbeta-crypto-pipeline/
├── pyproject.toml
├── README.md
├── .env.example
│
├── crypto_pipeline/
│   ├── __init__.py
│   ├── definitions.py          # Dagster definitions entry point
│   │
│   ├── assets/                 # Dagster software-defined assets
│   │   ├── __init__.py
│   │   ├── bronze/             # Raw data layer
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv.py
│   │   │   ├── funding_rates.py
│   │   │   ├── open_interest.py
│   │   │   └── token_info.py
│   │   ├── silver/             # Cleaned/normalized layer
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv_normalized.py
│   │   │   ├── funding_normalized.py
│   │   │   └── aggregated.py
│   │   └── gold/               # Published layer
│   │       ├── __init__.py
│   │       └── huggingface_datasets.py
│   │
│   ├── resources/              # Dagster resources (clients, connections)
│   │   ├── __init__.py
│   │   ├── cex_clients.py      # Exchange API clients
│   │   ├── storage.py          # Parquet I/O
│   │   └── huggingface.py      # HuggingFace publisher
│   │
│   ├── partitions/             # Partition definitions
│   │   ├── __init__.py
│   │   └── time_partitions.py
│   │
│   ├── sensors/                # Event-driven triggers
│   │   ├── __init__.py
│   │   └── new_data_sensor.py
│   │
│   ├── schedules/              # Time-based triggers
│   │   ├── __init__.py
│   │   └── daily_schedule.py
│   │
│   ├── jobs/                   # Job definitions
│   │   ├── __init__.py
│   │   ├── daily_job.py
│   │   └── backfill_job.py
│   │
│   ├── io_managers/            # Custom I/O managers
│   │   ├── __init__.py
│   │   └── parquet_io_manager.py
│   │
│   ├── types/                  # Pydantic models & type definitions
│   │   ├── __init__.py
│   │   ├── ohlcv.py
│   │   ├── funding.py
│   │   └── config.py
│   │
│   └── utils/                  # Shared utilities
│       ├── __init__.py
│       ├── rate_limiter.py
│       └── validators.py
│
├── tests/
│   ├── __init__.py
│   ├── test_assets/
│   ├── test_resources/
│   └── conftest.py
│
└── notebooks/                  # Development/exploration
    └── exploration.ipynb
```

---

## 1. Dagster Definitions Entry Point

```python
# crypto_pipeline/definitions.py
"""Dagster definitions - the main entry point for the pipeline."""

from dagster import Definitions, load_assets_from_modules

from crypto_pipeline.assets import bronze, silver, gold
from crypto_pipeline.resources import (
    BinanceClient,
    CoinbaseClient,
    OKXClient,
    ParquetIOManager,
    HuggingFaceResource,
)
from crypto_pipeline.jobs import daily_ingestion_job, backfill_job
from crypto_pipeline.schedules import daily_schedule
from crypto_pipeline.sensors import new_data_sensor

# Load all assets from modules
bronze_assets = load_assets_from_modules([bronze], group_name="bronze")
silver_assets = load_assets_from_modules([silver], group_name="silver")
gold_assets = load_assets_from_modules([gold], group_name="gold")

defs = Definitions(
    assets=[*bronze_assets, *silver_assets, *gold_assets],
    resources={
        "binance_client": BinanceClient(),
        "coinbase_client": CoinbaseClient(),
        "okx_client": OKXClient(),
        "parquet_io": ParquetIOManager(base_path="/data/warehouse"),
        "huggingface": HuggingFaceResource(),
    },
    jobs=[daily_ingestion_job, backfill_job],
    schedules=[daily_schedule],
    sensors=[new_data_sensor],
)
```

---

## 2. Type Definitions (Pydantic Models)

```python
# crypto_pipeline/types/ohlcv.py
"""Type definitions for OHLCV data."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
import pandas as pd

class OHLCVRecord(BaseModel):
    """Single OHLCV record with validation."""
    
    timestamp: datetime
    symbol: str
    exchange: str
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    quote_volume: Optional[float] = Field(default=None, ge=0)
    trades_count: Optional[int] = Field(default=None, ge=0)
    
    @field_validator('high')
    @classmethod
    def high_gte_low(cls, v, info):
        if 'low' in info.data and v < info.data['low']:
            raise ValueError('high must be >= low')
        return v
    
    @field_validator('symbol')
    @classmethod
    def normalize_symbol(cls, v):
        return v.upper().replace('/', '').replace('-', '')

    class Config:
        frozen = True


class OHLCVDataset(BaseModel):
    """Collection of OHLCV records with metadata."""
    
    records: List[OHLCVRecord]
    source_exchange: str
    fetch_timestamp: datetime
    partition_date: str  # YYYY-MM-DD
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame."""
        return pd.DataFrame([r.model_dump() for r in self.records])
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, exchange: str, partition_date: str):
        """Create from pandas DataFrame."""
        records = [OHLCVRecord(**row) for row in df.to_dict('records')]
        return cls(
            records=records,
            source_exchange=exchange,
            fetch_timestamp=datetime.utcnow(),
            partition_date=partition_date,
        )


# crypto_pipeline/types/config.py
"""Configuration types."""

from pydantic import BaseModel, SecretStr
from typing import List, Optional

class ExchangeConfig(BaseModel):
    """Configuration for a CEX."""
    
    name: str
    api_key: Optional[SecretStr] = None
    api_secret: Optional[SecretStr] = None
    rate_limit_per_minute: int = 1200
    base_url: str
    futures_url: Optional[str] = None
    enabled: bool = True


class PipelineConfig(BaseModel):
    """Global pipeline configuration."""
    
    symbols: List[str]
    exchanges: List[ExchangeConfig]
    data_warehouse_path: str = "/data/warehouse"
    huggingface_repo_id: str
    huggingface_token: SecretStr
    
    @classmethod
    def from_env(cls):
        """Load config from environment variables."""
        import os
        return cls(
            symbols=os.environ.get("SYMBOLS", "BTCUSDT,ETHUSDT").split(","),
            exchanges=[
                ExchangeConfig(
                    name="binance",
                    base_url="https://api.binance.com",
                    futures_url="https://fapi.binance.com",
                ),
            ],
            huggingface_repo_id=os.environ["HF_REPO_ID"],
            huggingface_token=SecretStr(os.environ["HF_TOKEN"]),
        )
```

---

## 3. Dagster Resources (Dependency Injection)

```python
# crypto_pipeline/resources/cex_clients.py
"""CEX API client resources."""

from dagster import ConfigurableResource, InitResourceContext
from pydantic import Field
import httpx
from typing import Optional
from datetime import datetime
import pandas as pd
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

from crypto_pipeline.utils.rate_limiter import AsyncRateLimiter


class BinanceClient(ConfigurableResource):
    """Binance API client as a Dagster resource."""
    
    base_url: str = "https://api.binance.com"
    futures_url: str = "https://fapi.binance.com"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    requests_per_minute: int = 1200
    
    _client: Optional[httpx.AsyncClient] = None
    _rate_limiter: Optional[AsyncRateLimiter] = None
    
    def setup_for_execution(self, context: InitResourceContext):
        """Initialize HTTP client and rate limiter."""
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"X-MBX-APIKEY": self.api_key} if self.api_key else {},
        )
        self._rate_limiter = AsyncRateLimiter(self.requests_per_minute)
    
    def teardown_after_execution(self, context: InitResourceContext):
        """Cleanup HTTP client."""
        if self._client:
            asyncio.run(self._client.aclose())
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    async def _request(self, url: str, params: dict = None) -> dict:
        """Make rate-limited request with retries."""
        await self._rate_limiter.acquire()
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def fetch_ohlcv(
        self, 
        symbol: str, 
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch OHLCV data with automatic pagination."""
        endpoint = f"{self.base_url}/api/v3/klines"
        
        all_candles = []
        current_start = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        
        while current_start < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": 1000,
            }
            
            candles = await self._request(endpoint, params)
            if not candles:
                break
            
            all_candles.extend(candles)
            current_start = candles[-1][0] + 1
        
        return self._parse_klines(all_candles)
    
    def _parse_klines(self, raw: list) -> pd.DataFrame:
        """Parse Binance klines response."""
        df = pd.DataFrame(raw, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades_count',
            'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        
        for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
            df[col] = df[col].astype(float)
        
        df['trades_count'] = df['trades_count'].astype(int)
        
        return df[['timestamp', 'open', 'high', 'low', 'close', 
                   'volume', 'quote_volume', 'trades_count']]
    
    async def fetch_funding_rates(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch perpetual funding rate history."""
        endpoint = f"{self.futures_url}/fapi/v1/fundingRate"
        
        all_rates = []
        current_start = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        
        while current_start < end_ms:
            params = {
                "symbol": symbol,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": 1000,
            }
            
            rates = await self._request(endpoint, params)
            if not rates:
                break
            
            all_rates.extend(rates)
            current_start = rates[-1]['fundingTime'] + 1
        
        df = pd.DataFrame(all_rates)
        df['timestamp'] = pd.to_datetime(df['fundingTime'], unit='ms', utc=True)
        df['funding_rate'] = df['fundingRate'].astype(float)
        df['mark_price'] = pd.to_numeric(df.get('markPrice'), errors='coerce')
        
        return df[['timestamp', 'funding_rate', 'mark_price']]
    
    async def fetch_open_interest(self, symbol: str) -> pd.DataFrame:
        """Fetch current open interest."""
        endpoint = f"{self.futures_url}/fapi/v1/openInterest"
        data = await self._request(endpoint, {"symbol": symbol})
        
        return pd.DataFrame([{
            'timestamp': pd.Timestamp.utcnow(),
            'open_interest': float(data['openInterest']),
        }])
    
    # Sync wrappers for non-async contexts
    def fetch_ohlcv_sync(self, *args, **kwargs) -> pd.DataFrame:
        return asyncio.run(self.fetch_ohlcv(*args, **kwargs))
    
    def fetch_funding_rates_sync(self, *args, **kwargs) -> pd.DataFrame:
        return asyncio.run(self.fetch_funding_rates(*args, **kwargs))
```

```python
# crypto_pipeline/resources/storage.py
"""Parquet storage resource."""

from dagster import ConfigurableIOManager, InputContext, OutputContext
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from typing import Optional


class ParquetIOManager(ConfigurableIOManager):
    """Custom I/O manager for partitioned parquet storage."""
    
    base_path: str = "/data/warehouse"
    
    def _get_path(self, context) -> Path:
        """Construct path from asset key and partition."""
        asset_key = "/".join(context.asset_key.path)
        
        if context.has_partition_key:
            partition = context.partition_key
            return Path(self.base_path) / asset_key / f"partition={partition}" / "data.parquet"
        
        return Path(self.base_path) / asset_key / "data.parquet"
    
    def handle_output(self, context: OutputContext, obj: pd.DataFrame):
        """Write DataFrame to parquet."""
        path = self._get_path(context)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add metadata
        metadata = {
            b"dagster_run_id": context.run_id.encode() if context.run_id else b"",
            b"asset_key": "/".join(context.asset_key.path).encode(),
        }
        
        table = pa.Table.from_pandas(obj)
        table = table.replace_schema_metadata({**table.schema.metadata, **metadata})
        
        pq.write_table(table, path, compression="snappy")
        
        context.log.info(f"Wrote {len(obj)} rows to {path}")
        
        # Log metadata for Dagster UI
        context.add_output_metadata({
            "row_count": len(obj),
            "path": str(path),
            "columns": list(obj.columns),
        })
    
    def load_input(self, context: InputContext) -> pd.DataFrame:
        """Read DataFrame from parquet."""
        path = self._get_path(context)
        
        if not path.exists():
            context.log.warning(f"No data found at {path}")
            return pd.DataFrame()
        
        return pq.read_table(path).to_pandas()
```

---

## 4. Bronze Layer Assets (Raw Data Ingestion)

```python
# crypto_pipeline/assets/bronze/ohlcv.py
"""Bronze layer: Raw OHLCV data from exchanges."""

from dagster import (
    asset,
    AssetExecutionContext,
    DailyPartitionsDefinition,
    MetadataValue,
    Output,
)
import pandas as pd
from datetime import datetime, timedelta

from crypto_pipeline.resources.cex_clients import BinanceClient

# Daily partitions starting from 2020
daily_partitions = DailyPartitionsDefinition(start_date="2020-01-01")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


@asset(
    partitions_def=daily_partitions,
    group_name="bronze",
    compute_kind="python",
    description="Raw OHLCV data from Binance",
    metadata={
        "source": "Binance API",
        "interval": "1d",
    },
)
def bronze_binance_ohlcv(
    context: AssetExecutionContext,
    binance_client: BinanceClient,
) -> Output[pd.DataFrame]:
    """Fetch daily OHLCV from Binance for all configured symbols."""
    
    partition_date = context.partition_key
    start = datetime.strptime(partition_date, "%Y-%m-%d")
    end = start + timedelta(days=1)
    
    context.log.info(f"Fetching OHLCV for {partition_date}")
    
    all_data = []
    
    for symbol in SYMBOLS:
        try:
            df = binance_client.fetch_ohlcv_sync(
                symbol=symbol,
                interval="1d",
                start=start,
                end=end,
            )
            df['symbol'] = symbol
            df['exchange'] = 'binance'
            all_data.append(df)
            
            context.log.info(f"Fetched {len(df)} rows for {symbol}")
            
        except Exception as e:
            context.log.error(f"Failed to fetch {symbol}: {e}")
    
    if not all_data:
        return Output(
            pd.DataFrame(),
            metadata={"row_count": 0, "status": "no_data"},
        )
    
    result = pd.concat(all_data, ignore_index=True)
    
    return Output(
        result,
        metadata={
            "row_count": len(result),
            "symbols": MetadataValue.json(SYMBOLS),
            "partition_date": partition_date,
        },
    )


@asset(
    partitions_def=daily_partitions,
    group_name="bronze",
    compute_kind="python",
    description="Raw OHLCV data from Coinbase",
)
def bronze_coinbase_ohlcv(
    context: AssetExecutionContext,
    coinbase_client,  # CoinbaseClient resource
) -> Output[pd.DataFrame]:
    """Fetch daily OHLCV from Coinbase."""
    # Similar implementation...
    pass


@asset(
    partitions_def=daily_partitions,
    group_name="bronze",
    compute_kind="python", 
    description="Raw OHLCV data from OKX",
)
def bronze_okx_ohlcv(
    context: AssetExecutionContext,
    okx_client,  # OKXClient resource
) -> Output[pd.DataFrame]:
    """Fetch daily OHLCV from OKX."""
    # Similar implementation...
    pass
```

```python
# crypto_pipeline/assets/bronze/funding_rates.py
"""Bronze layer: Raw funding rate data."""

from dagster import asset, AssetExecutionContext, DailyPartitionsDefinition, Output
import pandas as pd
from datetime import datetime, timedelta

daily_partitions = DailyPartitionsDefinition(start_date="2021-01-01")

PERP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@asset(
    partitions_def=daily_partitions,
    group_name="bronze",
    compute_kind="python",
    description="Raw funding rates from Binance Futures",
)
def bronze_binance_funding(
    context: AssetExecutionContext,
    binance_client,
) -> Output[pd.DataFrame]:
    """Fetch funding rate data from Binance."""
    
    partition_date = context.partition_key
    start = datetime.strptime(partition_date, "%Y-%m-%d")
    end = start + timedelta(days=1)
    
    all_data = []
    
    for symbol in PERP_SYMBOLS:
        try:
            df = binance_client.fetch_funding_rates_sync(
                symbol=symbol,
                start=start,
                end=end,
            )
            df['symbol'] = symbol
            df['exchange'] = 'binance'
            all_data.append(df)
            
        except Exception as e:
            context.log.error(f"Failed to fetch funding for {symbol}: {e}")
    
    result = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
    
    return Output(
        result,
        metadata={"row_count": len(result), "partition_date": partition_date},
    )
```

---

## 5. Silver Layer Assets (Cleaned & Normalized)

```python
# crypto_pipeline/assets/silver/ohlcv_normalized.py
"""Silver layer: Normalized and validated OHLCV data."""

from dagster import asset, AssetExecutionContext, AssetIn, Output
import pandas as pd
import numpy as np

from crypto_pipeline.types.ohlcv import OHLCVRecord
from crypto_pipeline.utils.validators import validate_ohlcv


@asset(
    ins={
        "binance": AssetIn(key="bronze_binance_ohlcv"),
        "coinbase": AssetIn(key="bronze_coinbase_ohlcv"),
        "okx": AssetIn(key="bronze_okx_ohlcv"),
    },
    group_name="silver",
    compute_kind="python",
    description="Normalized OHLCV from all exchanges",
)
def silver_ohlcv_normalized(
    context: AssetExecutionContext,
    binance: pd.DataFrame,
    coinbase: pd.DataFrame,
    okx: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Combine and normalize OHLCV from all exchanges."""
    
    # Combine all sources
    dfs = [df for df in [binance, coinbase, okx] if not df.empty]
    
    if not dfs:
        return Output(pd.DataFrame(), metadata={"row_count": 0})
    
    combined = pd.concat(dfs, ignore_index=True)
    
    # Normalize columns
    combined['timestamp'] = pd.to_datetime(combined['timestamp'], utc=True)
    combined['symbol'] = combined['symbol'].str.upper().str.replace('/', '').str.replace('-', '')
    combined['exchange'] = combined['exchange'].str.lower()
    
    # Validate
    validation_result = validate_ohlcv(combined)
    
    if validation_result.errors:
        context.log.error(f"Validation errors: {validation_result.errors}")
    
    if validation_result.warnings:
        context.log.warning(f"Validation warnings: {validation_result.warnings}")
    
    # Remove invalid rows
    valid_mask = (
        (combined['high'] >= combined['low']) &
        (combined['high'] >= combined['open']) &
        (combined['high'] >= combined['close']) &
        (combined['low'] <= combined['open']) &
        (combined['low'] <= combined['close']) &
        (combined['volume'] >= 0)
    )
    
    cleaned = combined[valid_mask].copy()
    removed_count = len(combined) - len(cleaned)
    
    if removed_count > 0:
        context.log.warning(f"Removed {removed_count} invalid rows")
    
    # Sort and deduplicate
    cleaned = cleaned.sort_values(['timestamp', 'symbol', 'exchange'])
    cleaned = cleaned.drop_duplicates(
        subset=['timestamp', 'symbol', 'exchange'],
        keep='last'
    )
    
    return Output(
        cleaned,
        metadata={
            "row_count": len(cleaned),
            "exchanges": list(cleaned['exchange'].unique()),
            "symbols": list(cleaned['symbol'].unique()),
            "removed_invalid": removed_count,
        },
    )


@asset(
    ins={"normalized": AssetIn(key="silver_ohlcv_normalized")},
    group_name="silver",
    compute_kind="python",
    description="Cross-exchange aggregated OHLCV",
)
def silver_ohlcv_aggregated(
    context: AssetExecutionContext,
    normalized: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Aggregate OHLCV across exchanges (volume-weighted)."""
    
    if normalized.empty:
        return Output(pd.DataFrame(), metadata={"row_count": 0})
    
    # Find primary exchange (highest volume) for open/close
    idx = normalized.groupby(['timestamp', 'symbol'])['volume'].idxmax()
    primary = normalized.loc[idx][['timestamp', 'symbol', 'open', 'close']]
    
    # Aggregate other fields
    agg = normalized.groupby(['timestamp', 'symbol']).agg({
        'high': 'max',
        'low': 'min',
        'volume': 'sum',
        'quote_volume': 'sum',
        'trades_count': 'sum',
    }).reset_index()
    
    # Merge
    result = primary.merge(agg, on=['timestamp', 'symbol'])
    result['exchange'] = 'aggregated'
    
    return Output(
        result,
        metadata={
            "row_count": len(result),
            "symbols": list(result['symbol'].unique()),
        },
    )
```

---

## 6. Gold Layer Assets (Published Datasets)

```python
# crypto_pipeline/assets/gold/huggingface_datasets.py
"""Gold layer: Published datasets to HuggingFace."""

from dagster import asset, AssetExecutionContext, AssetIn, Output
import pandas as pd
from pathlib import Path

from crypto_pipeline.resources.huggingface import HuggingFaceResource


@asset(
    ins={
        "ohlcv": AssetIn(key="silver_ohlcv_aggregated"),
        "funding": AssetIn(key="silver_funding_normalized"),
    },
    group_name="gold",
    compute_kind="python",
    description="Published OHLCV dataset on HuggingFace",
)
def gold_huggingface_ohlcv(
    context: AssetExecutionContext,
    huggingface: HuggingFaceResource,
    ohlcv: pd.DataFrame,
    funding: pd.DataFrame,
) -> Output[dict]:
    """Publish datasets to HuggingFace."""
    
    if ohlcv.empty:
        context.log.warning("No OHLCV data to publish")
        return Output({"status": "skipped"})
    
    # Write to temp parquet
    temp_path = Path("/tmp/publish")
    temp_path.mkdir(exist_ok=True)
    
    ohlcv_path = temp_path / "ohlcv_daily.parquet"
    ohlcv.to_parquet(ohlcv_path, compression="snappy")
    
    funding_path = temp_path / "funding_rates.parquet"
    if not funding.empty:
        funding.to_parquet(funding_path, compression="snappy")
    
    # Publish
    result = huggingface.publish({
        "ohlcv_daily": ohlcv_path,
        "funding_rates": funding_path,
    })
    
    return Output(
        result,
        metadata={
            "ohlcv_rows": len(ohlcv),
            "funding_rows": len(funding),
            "huggingface_url": result.get("url", ""),
        },
    )
```

---

## 7. Schedules and Jobs

```python
# crypto_pipeline/schedules/daily_schedule.py
"""Schedule definitions."""

from dagster import (
    ScheduleDefinition,
    build_schedule_from_partitioned_job,
    define_asset_job,
)

# Job that materializes all daily partitioned assets
daily_ingestion_job = define_asset_job(
    name="daily_ingestion_job",
    selection=[
        "bronze_binance_ohlcv",
        "bronze_coinbase_ohlcv",
        "bronze_okx_ohlcv",
        "bronze_binance_funding",
        "silver_ohlcv_normalized",
        "silver_ohlcv_aggregated",
        "silver_funding_normalized",
    ],
    partitions_def=daily_partitions,
)

# Schedule that runs daily at 1 AM UTC
daily_schedule = build_schedule_from_partitioned_job(
    job=daily_ingestion_job,
    hour_of_day=1,
    minute_of_hour=0,
)


# Separate job for publishing (runs after ingestion)
publish_job = define_asset_job(
    name="publish_job",
    selection=["gold_huggingface_ohlcv"],
)

publish_schedule = ScheduleDefinition(
    job=publish_job,
    cron_schedule="0 2 * * *",  # 2 AM UTC daily
)
```

```python
# crypto_pipeline/jobs/backfill_job.py
"""Backfill job for historical data."""

from dagster import define_asset_job

backfill_job = define_asset_job(
    name="backfill_job",
    selection=[
        "bronze_binance_ohlcv",
        "silver_ohlcv_normalized",
        "silver_ohlcv_aggregated",
    ],
    description="Backfill historical data for a date range",
)
```

---

## 8. Utilities

```python
# crypto_pipeline/utils/rate_limiter.py
"""Async rate limiter for API calls."""

import asyncio
from time import time


class AsyncRateLimiter:
    """Token bucket rate limiter for async operations."""
    
    def __init__(self, requests_per_minute: int):
        self.rate = requests_per_minute / 60.0  # requests per second
        self.tokens = requests_per_minute
        self.max_tokens = requests_per_minute
        self.last_update = time()
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1
```

```python
# crypto_pipeline/utils/validators.py
"""Data validation utilities."""

from dataclasses import dataclass
from typing import List
import pandas as pd


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]


def validate_ohlcv(df: pd.DataFrame) -> ValidationResult:
    """Validate OHLCV DataFrame."""
    errors = []
    warnings = []
    
    required = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in required if c not in df.columns]
    if missing:
        errors.append(f"Missing columns: {missing}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)
    
    # OHLC relationship checks
    invalid_high = len(df[df['high'] < df[['open', 'close', 'low']].max(axis=1)])
    if invalid_high > 0:
        errors.append(f"Invalid high values: {invalid_high} rows")
    
    invalid_low = len(df[df['low'] > df[['open', 'close', 'high']].min(axis=1)])
    if invalid_low > 0:
        errors.append(f"Invalid low values: {invalid_low} rows")
    
    # Negative checks
    negative_price = len(df[(df[['open', 'high', 'low', 'close']] < 0).any(axis=1)])
    if negative_price > 0:
        errors.append(f"Negative prices: {negative_price} rows")
    
    negative_volume = len(df[df['volume'] < 0])
    if negative_volume > 0:
        errors.append(f"Negative volume: {negative_volume} rows")
    
    # Duplicates (warning)
    duplicates = len(df[df.duplicated(subset=['timestamp', 'symbol', 'exchange'])])
    if duplicates > 0:
        warnings.append(f"Duplicate rows: {duplicates}")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
```

---

## 9. Running the Pipeline

### Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Start Dagster UI (dagit)
dagster dev -m crypto_pipeline.definitions

# Run a specific job
dagster job execute -m crypto_pipeline.definitions -j daily_ingestion_job

# Backfill historical data
dagster job backfill -m crypto_pipeline.definitions -j backfill_job \
    --partition-range 2024-01-01...2024-12-01
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install -e .

COPY crypto_pipeline/ crypto_pipeline/

# Dagster daemon for schedules/sensors
CMD ["dagster-daemon", "run"]
```

```yaml
# docker-compose.yml
version: "3.8"

services:
  dagster-webserver:
    build: .
    command: dagster-webserver -h 0.0.0.0 -p 3000 -m crypto_pipeline.definitions
    ports:
      - "3000:3000"
    environment:
      - HF_TOKEN=${HF_TOKEN}
      - HF_REPO_ID=${HF_REPO_ID}
    volumes:
      - ./data:/data

  dagster-daemon:
    build: .
    command: dagster-daemon run
    environment:
      - HF_TOKEN=${HF_TOKEN}
      - HF_REPO_ID=${HF_REPO_ID}
    volumes:
      - ./data:/data
```

---

## 10. Dependencies

```toml
[project]
name = "defeatbeta-crypto-pipeline"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    # Orchestration
    "dagster >= 1.7.0",
    "dagster-webserver >= 1.7.0",
    
    # Data processing
    "pandas >= 2.2.0",
    "pyarrow >= 15.0.0",
    "pydantic >= 2.5.0",
    
    # HTTP clients
    "httpx >= 0.27.0",
    "tenacity >= 8.2.0",
    
    # HuggingFace
    "huggingface_hub >= 0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest >= 8.0.0",
    "pytest-asyncio >= 0.23.0",
    "dagster-webserver >= 1.7.0",
]
```

---

## Key Improvements Over Previous Design

| Aspect | Previous | New (Dagster) |
|--------|----------|---------------|
| Orchestration | APScheduler scripts | Dagster jobs/schedules |
| Data Model | Loose DataFrames | Pydantic-validated assets |
| Lineage | None | Built-in asset graph |
| Partitioning | Manual | Native daily partitions |
| Backfills | Custom scripts | `dagster job backfill` |
| Monitoring | Custom logging | Dagster UI + metrics |
| Testing | Manual | Asset unit tests |
| Dependencies | Implicit | Explicit via `AssetIn` |
| Incremental | None | Partition-based |
