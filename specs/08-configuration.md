# 08 - Configuration Management

> Environment variables, secrets management, and multi-environment setup

## Configuration Philosophy

1. **12-Factor App**: Configuration via environment variables
2. **No Secrets in Code**: All secrets from environment or secret managers
3. **Fail Fast**: Validate configuration at startup
4. **Type-Safe**: Pydantic models for configuration
5. **Environment Parity**: Same config structure across dev/staging/prod

---

## 1. Environment Variables

### Pipeline Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYMBOLS` | No | `BTCUSDT,ETHUSDT` | Comma-separated trading pairs |
| `EXCHANGES` | No | `binance` | Comma-separated exchanges |
| `DATA_WAREHOUSE_PATH` | No | `/data/warehouse` | Local parquet storage path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `DAGSTER_HOME` | No | `~/.dagster` | Dagster home directory |

### Exchange API Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BINANCE_API_KEY` | No | - | Binance API key (optional for public data) |
| `BINANCE_API_SECRET` | No | - | Binance API secret |
| `BINANCE_RATE_LIMIT` | No | `1200` | Requests per minute |
| `COINBASE_API_KEY` | No | - | Coinbase API key |
| `COINBASE_API_SECRET` | No | - | Coinbase API secret |
| `OKX_API_KEY` | No | - | OKX API key |
| `OKX_API_SECRET` | No | - | OKX API secret |
| `OKX_PASSPHRASE` | No | - | OKX API passphrase |

### HuggingFace Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HF_TOKEN` | **Yes** | - | HuggingFace API token |
| `HF_REPO_ID` | **Yes** | - | Dataset repository ID |
| `HF_REPO_TYPE` | No | `dataset` | Repository type |

### Client Library Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CRYPTO_DATA_REPO` | No | `yourorg/crypto-cex-data` | HuggingFace dataset repo |
| `DUCKDB_MEMORY_LIMIT` | No | `80%` | DuckDB memory limit |
| `DUCKDB_THREADS` | No | `4` | DuckDB thread count |
| `HTTP_PROXY` | No | - | HTTP proxy URL |
| `CACHE_DIR` | No | `/tmp/crypto_cache` | Local cache directory |

---

## 2. Pydantic Configuration Models

### Pipeline Configuration

```python
# crypto_pipeline/types/config.py
from pydantic import BaseModel, SecretStr, Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class ExchangeConfig(BaseModel):
    """Configuration for a single exchange."""
    
    name: str
    api_key: Optional[SecretStr] = None
    api_secret: Optional[SecretStr] = None
    passphrase: Optional[SecretStr] = None  # For OKX
    rate_limit_per_minute: int = 1200
    enabled: bool = True
    
    @property
    def has_credentials(self) -> bool:
        return self.api_key is not None and self.api_secret is not None


class HuggingFaceConfig(BaseModel):
    """HuggingFace publishing configuration."""
    
    token: SecretStr
    repo_id: str
    repo_type: str = "dataset"
    
    @field_validator('repo_id')
    @classmethod
    def validate_repo_id(cls, v):
        if '/' not in v:
            raise ValueError("repo_id must be in format 'org/repo-name'")
        return v


class PipelineSettings(BaseSettings):
    """Main pipeline settings loaded from environment."""
    
    # Symbols and exchanges
    symbols: List[str] = Field(default=["BTCUSDT", "ETHUSDT"])
    exchanges: List[str] = Field(default=["binance"])
    
    # Storage
    data_warehouse_path: str = "/data/warehouse"
    
    # Logging
    log_level: str = "INFO"
    
    # HuggingFace
    hf_token: SecretStr
    hf_repo_id: str
    
    # Exchange credentials (optional)
    binance_api_key: Optional[SecretStr] = None
    binance_api_secret: Optional[SecretStr] = None
    binance_rate_limit: int = 1200
    
    coinbase_api_key: Optional[SecretStr] = None
    coinbase_api_secret: Optional[SecretStr] = None
    
    okx_api_key: Optional[SecretStr] = None
    okx_api_secret: Optional[SecretStr] = None
    okx_passphrase: Optional[SecretStr] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @field_validator('symbols', mode='before')
    @classmethod
    def parse_symbols(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(',')]
        return v
    
    @field_validator('exchanges', mode='before')
    @classmethod
    def parse_exchanges(cls, v):
        if isinstance(v, str):
            return [e.strip() for e in v.split(',')]
        return v
    
    def get_exchange_config(self, name: str) -> ExchangeConfig:
        """Get configuration for a specific exchange."""
        configs = {
            'binance': ExchangeConfig(
                name='binance',
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
                rate_limit_per_minute=self.binance_rate_limit,
            ),
            'coinbase': ExchangeConfig(
                name='coinbase',
                api_key=self.coinbase_api_key,
                api_secret=self.coinbase_api_secret,
            ),
            'okx': ExchangeConfig(
                name='okx',
                api_key=self.okx_api_key,
                api_secret=self.okx_api_secret,
                passphrase=self.okx_passphrase,
            ),
        }
        
        if name not in configs:
            raise ValueError(f"Unknown exchange: {name}")
        
        return configs[name]
    
    def get_huggingface_config(self) -> HuggingFaceConfig:
        """Get HuggingFace configuration."""
        return HuggingFaceConfig(
            token=self.hf_token,
            repo_id=self.hf_repo_id,
        )


# Singleton instance
_settings: Optional[PipelineSettings] = None

def get_settings() -> PipelineSettings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = PipelineSettings()
    return _settings
```

### Client Library Configuration

```python
# defeatbeta_crypto/config.py
from pydantic_settings import BaseSettings
from typing import Optional


class ClientSettings(BaseSettings):
    """Client library settings."""
    
    # Data source
    crypto_data_repo: str = "yourorg/crypto-cex-data"
    
    # DuckDB settings
    duckdb_memory_limit: str = "80%"
    duckdb_threads: int = 4
    
    # HTTP settings
    http_proxy: Optional[str] = None
    http_timeout: int = 30
    http_retries: int = 3
    
    # Cache settings
    cache_dir: str = "/tmp/crypto_cache"
    cache_enabled: bool = True
    
    class Config:
        env_prefix = "CRYPTO_"
        env_file = ".env"
```

---

## 3. Environment Files

### Development (.env.development)

```bash
# .env.development
# Development environment configuration

# Logging
LOG_LEVEL=DEBUG

# Symbols (minimal for dev)
SYMBOLS=BTCUSDT,ETHUSDT

# Exchanges
EXCHANGES=binance

# Storage
DATA_WAREHOUSE_PATH=./data/dev_warehouse

# HuggingFace (use test repo)
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
HF_REPO_ID=yourorg/crypto-cex-data-dev

# Rate limits (lower for dev)
BINANCE_RATE_LIMIT=120

# DuckDB
DUCKDB_MEMORY_LIMIT=4GB
DUCKDB_THREADS=2
```

### Staging (.env.staging)

```bash
# .env.staging
# Staging environment configuration

LOG_LEVEL=INFO

SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT

EXCHANGES=binance,coinbase

DATA_WAREHOUSE_PATH=/data/staging_warehouse

HF_TOKEN=${HF_TOKEN}  # From secrets manager
HF_REPO_ID=yourorg/crypto-cex-data-staging

BINANCE_RATE_LIMIT=600

DUCKDB_MEMORY_LIMIT=8GB
DUCKDB_THREADS=4
```

### Production (.env.production)

```bash
# .env.production
# Production environment configuration

LOG_LEVEL=INFO

# Full symbol list
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,DOTUSDT,MATICUSDT

# All exchanges
EXCHANGES=binance,coinbase,okx,bybit

DATA_WAREHOUSE_PATH=/data/warehouse

# Production HuggingFace repo
HF_TOKEN=${HF_TOKEN}
HF_REPO_ID=yourorg/crypto-cex-data

# Full rate limits
BINANCE_RATE_LIMIT=1200

DUCKDB_MEMORY_LIMIT=80%
DUCKDB_THREADS=8
```

### Example Template (.env.example)

```bash
# .env.example
# Copy this file to .env and fill in values

# ===================
# Required Settings
# ===================

# HuggingFace (required for publishing)
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
HF_REPO_ID=yourorg/crypto-cex-data

# ===================
# Optional Settings
# ===================

# Symbols to track (comma-separated)
# SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT

# Exchanges to fetch from (comma-separated)
# EXCHANGES=binance,coinbase,okx

# Logging level (DEBUG, INFO, WARNING, ERROR)
# LOG_LEVEL=INFO

# Data warehouse path
# DATA_WAREHOUSE_PATH=/data/warehouse

# ===================
# Exchange API Keys
# ===================
# Only needed for authenticated endpoints (not required for public data)

# Binance
# BINANCE_API_KEY=
# BINANCE_API_SECRET=

# Coinbase
# COINBASE_API_KEY=
# COINBASE_API_SECRET=

# OKX
# OKX_API_KEY=
# OKX_API_SECRET=
# OKX_PASSPHRASE=

# ===================
# Advanced Settings
# ===================

# HTTP proxy
# HTTP_PROXY=http://proxy.example.com:8080

# Rate limits (requests per minute)
# BINANCE_RATE_LIMIT=1200

# DuckDB settings
# DUCKDB_MEMORY_LIMIT=80%
# DUCKDB_THREADS=4
```

---

## 4. Multi-Environment Setup

### Environment Detection

```python
# crypto_pipeline/utils/env.py
import os
from enum import Enum
from typing import Optional


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


def get_environment() -> Environment:
    """Detect current environment."""
    env_name = os.environ.get("ENVIRONMENT", "development").lower()
    
    try:
        return Environment(env_name)
    except ValueError:
        return Environment.DEVELOPMENT


def is_production() -> bool:
    return get_environment() == Environment.PRODUCTION


def is_development() -> bool:
    return get_environment() == Environment.DEVELOPMENT


def is_test() -> bool:
    return get_environment() == Environment.TEST
```

### Environment-Specific Loading

```python
# crypto_pipeline/config_loader.py
from pathlib import Path
from dotenv import load_dotenv

from crypto_pipeline.utils.env import get_environment, Environment


def load_environment_config():
    """Load environment-specific configuration."""
    env = get_environment()
    
    # Base .env file
    base_env = Path(".env")
    if base_env.exists():
        load_dotenv(base_env)
    
    # Environment-specific file
    env_files = {
        Environment.DEVELOPMENT: ".env.development",
        Environment.STAGING: ".env.staging",
        Environment.PRODUCTION: ".env.production",
        Environment.TEST: ".env.test",
    }
    
    env_file = Path(env_files.get(env, ".env"))
    if env_file.exists():
        load_dotenv(env_file, override=True)
```

---

## 5. Dagster Configuration

### Dagster Resource Configuration

```python
# crypto_pipeline/definitions.py
from dagster import Definitions, EnvVar

from crypto_pipeline.resources import BinanceClient, ParquetIOManager, HuggingFaceResource


defs = Definitions(
    resources={
        # Resources configured via environment variables
        "binance_client": BinanceClient(
            api_key=EnvVar("BINANCE_API_KEY").get_value() or None,
            api_secret=EnvVar("BINANCE_API_SECRET").get_value() or None,
            requests_per_minute=int(EnvVar("BINANCE_RATE_LIMIT").get_value() or "1200"),
        ),
        "parquet_io": ParquetIOManager(
            base_path=EnvVar("DATA_WAREHOUSE_PATH").get_value() or "/data/warehouse",
        ),
        "huggingface": HuggingFaceResource(
            token=EnvVar("HF_TOKEN"),
            repo_id=EnvVar("HF_REPO_ID"),
        ),
    },
    # ... assets, jobs, schedules
)
```

### Dagster Workspace Configuration

```yaml
# workspace.yaml
load_from:
  - python_module:
      module_name: crypto_pipeline.definitions
      working_directory: .
```

### dagster.yaml (Instance Configuration)

```yaml
# dagster.yaml
scheduler:
  module: dagster.core.scheduler
  class: DagsterDaemonScheduler

run_coordinator:
  module: dagster.core.run_coordinator
  class: QueuedRunCoordinator
  config:
    max_concurrent_runs: 5

run_storage:
  module: dagster.core.storage.runs
  class: SqliteRunStorage
  config:
    base_dir: ${DAGSTER_HOME}/storage

event_log_storage:
  module: dagster.core.storage.event_log
  class: SqliteEventLogStorage
  config:
    base_dir: ${DAGSTER_HOME}/storage

schedule_storage:
  module: dagster.core.storage.schedules
  class: SqliteScheduleStorage
  config:
    base_dir: ${DAGSTER_HOME}/storage

telemetry:
  enabled: false
```

---

## 6. Docker Configuration

### Docker Environment Variables

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Build args
ARG ENVIRONMENT=production

# Environment
ENV ENVIRONMENT=${ENVIRONMENT}
ENV PYTHONUNBUFFERED=1
ENV DAGSTER_HOME=/opt/dagster/dagster_home

# ... rest of Dockerfile
```

### Docker Compose Environment

```yaml
# docker-compose.yml
version: "3.8"

services:
  dagster-webserver:
    build:
      context: .
      args:
        ENVIRONMENT: ${ENVIRONMENT:-production}
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - HF_TOKEN=${HF_TOKEN}
      - HF_REPO_ID=${HF_REPO_ID}
      - BINANCE_API_KEY=${BINANCE_API_KEY:-}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET:-}
      - DATA_WAREHOUSE_PATH=/data/warehouse
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    env_file:
      - .env.${ENVIRONMENT:-production}
    volumes:
      - warehouse_data:/data/warehouse
```

---

## 7. Secrets Management

### Local Development

```bash
# Use .env file (never commit!)
cp .env.example .env
# Edit .env with your secrets
```

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          BINANCE_API_KEY: ${{ secrets.BINANCE_API_KEY }}
        run: |
          # Deploy with secrets
```

### Cloud Secrets (AWS Example)

```python
# crypto_pipeline/utils/secrets.py
import boto3
import json
from functools import lru_cache


@lru_cache
def get_secret(secret_name: str) -> dict:
    """Fetch secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])


def load_exchange_secrets():
    """Load exchange API keys from secrets manager."""
    secrets = get_secret("crypto-pipeline/exchange-keys")
    
    import os
    os.environ['BINANCE_API_KEY'] = secrets.get('binance_api_key', '')
    os.environ['BINANCE_API_SECRET'] = secrets.get('binance_api_secret', '')
    # ... other exchanges
```

---

## 8. Configuration Validation

```python
# crypto_pipeline/utils/validate_config.py
import sys
from crypto_pipeline.types.config import PipelineSettings
from pydantic import ValidationError


def validate_configuration():
    """Validate configuration at startup."""
    try:
        settings = PipelineSettings()
        
        # Additional validation
        if not settings.hf_token:
            raise ValueError("HF_TOKEN is required")
        
        if not settings.hf_repo_id:
            raise ValueError("HF_REPO_ID is required")
        
        print(f"Configuration valid for {len(settings.symbols)} symbols")
        print(f"Exchanges: {', '.join(settings.exchanges)}")
        
        return settings
        
    except ValidationError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    validate_configuration()
```

---

## Configuration Checklist

### Before First Run

- [ ] Copy `.env.example` to `.env`
- [ ] Set `HF_TOKEN` with valid HuggingFace token
- [ ] Set `HF_REPO_ID` to target dataset repository
- [ ] (Optional) Add exchange API keys for authenticated endpoints
- [ ] Run `python -m crypto_pipeline.utils.validate_config`

### Before Production Deploy

- [ ] Use secrets manager for all credentials
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure proper `DATA_WAREHOUSE_PATH`
- [ ] Set appropriate rate limits
- [ ] Enable monitoring/alerting
