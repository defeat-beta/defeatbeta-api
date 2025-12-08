# 04 - Client Library

> Consumer library design and API specifications

## Library Structure

```
defeatbeta-crypto-api/
├── defeatbeta_crypto/
│   ├── __init__.py              # Package init, welcome banner
│   ├── __version__.py           # Version string
│   ├── client/
│   │   ├── __init__.py
│   │   ├── duckdb_client.py     # DuckDB connection singleton
│   │   ├── duckdb_conf.py       # DuckDB configuration
│   │   └── huggingface_client.py # HuggingFace URL resolution
│   ├── data/
│   │   ├── __init__.py
│   │   ├── token.py             # Main Token class
│   │   ├── market.py            # Market-wide queries
│   │   ├── exchange.py          # Exchange-specific queries
│   │   ├── sql/
│   │   │   ├── sql_loader.py
│   │   │   ├── select_ohlcv.sql
│   │   │   ├── select_funding.sql
│   │   │   ├── select_oi.sql
│   │   │   └── ...
│   │   └── template/
│   │       ├── token_categories.json
│   │       └── exchange_symbols.json
│   ├── reports/
│   │   ├── tearsheet.py
│   │   └── tearsheet.html
│   └── utils/
│       ├── __init__.py
│       ├── const.py
│       └── util.py
├── tests/
├── notebooks/
├── pyproject.toml
└── README.md
```

## Core Components

### HuggingFace Client

```python
# defeatbeta_crypto/client/huggingface_client.py

from typing import Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from defeatbeta_crypto.utils.const import TABLES

class HuggingFaceClient:
    """Client for resolving HuggingFace dataset URLs"""
    
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.base_url = "https://huggingface.co/datasets/yourorg/crypto-cex-data"
        self.timeout = timeout
        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _make_request(self, url: str) -> Dict[str, Any]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "defeatbeta-crypto/1.0"},
                verify=True
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request to {url} failed: {e}")

    def get_data_update_time(self) -> str:
        """Get the last update time from spec.json"""
        url = f"{self.base_url}/resolve/main/spec.json"
        data = self._make_request(url)
        if "update_time" not in data:
            raise ValueError("Missing 'update_time' field in spec.json")
        return data["update_time"]

    def get_url_path(self, table: str) -> str:
        """Get the full URL for a parquet table"""
        if table not in TABLES:
            raise ValueError(
                f"Invalid table '{table}'. Valid options are: {', '.join(TABLES)}"
            )
        return f"{self.base_url}/resolve/main/data/{table}.parquet"
    
    def get_spec(self) -> Dict[str, Any]:
        """Get full spec.json content"""
        url = f"{self.base_url}/resolve/main/spec.json"
        return self._make_request(url)
```

### DuckDB Client (Singleton Pattern)

```python
# defeatbeta_crypto/client/duckdb_client.py

import logging
import sys
import time
from contextlib import contextmanager
from threading import Lock
from typing import Optional

import duckdb
import pandas as pd

from defeatbeta_crypto import data_update_time
from defeatbeta_crypto.client.duckdb_conf import Configuration

_instance = None
_lock = Lock()

def get_duckdb_client(http_proxy=None, log_level=None, config=None):
    """Get or create singleton DuckDB client"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = DuckDBClient(http_proxy, log_level, config)
    return _instance

class DuckDBClient:
    """DuckDB client with cache_httpfs for remote parquet queries"""
    
    def __init__(self, http_proxy: Optional[str] = None, 
                 log_level: Optional[str] = logging.INFO,
                 config: Optional[Configuration] = None):
        self.connection = None
        self.http_proxy = http_proxy
        self.config = config if config is not None else Configuration()
        self.log_level = log_level
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._initialize_connection()
        self._validate_httpfs_cache()

    def _initialize_connection(self) -> None:
        """Initialize DuckDB with cache_httpfs extension"""
        try:
            self.connection = duckdb.connect(":memory:")
            self.logger.debug("DuckDB connection initialized.")

            duckdb_settings = self.config.get_duckdb_settings()
            if self.http_proxy:
                duckdb_settings.append(f"SET GLOBAL http_proxy = '{self.http_proxy}';")

            for query in duckdb_settings:
                self.logger.debug(f"DuckDB settings: {query}")
                self.connection.execute(query)
                
        except Exception as e:
            self.logger.error(f"Failed to initialize connection: {str(e)}")
            raise

    def _validate_httpfs_cache(self):
        """Clear cache if remote data is newer than cached"""
        try:
            current_spec = self.query(
                "SELECT * FROM 'https://huggingface.co/datasets/yourorg/crypto-cex-data/resolve/main/spec.json'"
            )
            current_update_time = current_spec['update_time'].iloc[0]
            
            if current_update_time != data_update_time:
                self.logger.debug(f"Cache stale, clearing. Local: {data_update_time}, Remote: {current_update_time}")
                self.query("SELECT cache_httpfs_clear_cache()")
                
        except Exception as e:
            self.logger.warning(f"Cache validation failed: {str(e)}")

    @contextmanager
    def _get_cursor(self):
        cursor = self.connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def query(self, sql: str) -> pd.DataFrame:
        """Execute SQL query and return DataFrame"""
        self.logger.debug(f"Executing query: {sql[:200]}...")
        try:
            start_time = time.perf_counter()
            with self._get_cursor() as cursor:
                result = cursor.sql(sql).df()
                duration = time.perf_counter() - start_time
                self.logger.debug(
                    f"Query executed. Rows: {len(result)}, Time: {duration:.2f}s"
                )
                return result
        except Exception as e:
            self.logger.error(f"Query failed: {str(e)}")
            raise

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
```

### Token Class (Main Entry Point)

```python
# defeatbeta_crypto/data/token.py

import logging
from typing import Optional, List
import pandas as pd
import numpy as np

from defeatbeta_crypto.client.duckdb_client import get_duckdb_client
from defeatbeta_crypto.client.duckdb_conf import Configuration
from defeatbeta_crypto.client.huggingface_client import HuggingFaceClient
from defeatbeta_crypto.data.sql.sql_loader import load_sql
from defeatbeta_crypto.utils.const import (
    ohlcv_daily, ohlcv_hourly, funding_rates, 
    open_interest, liquidations, token_info
)

class Token:
    """Main entry point for cryptocurrency market data
    
    Similar to defeatbeta_api.Ticker but for crypto assets.
    
    Example:
        >>> from defeatbeta_crypto import Token
        >>> btc = Token("BTC")
        >>> btc.ohlcv()  # Daily OHLCV data
        >>> btc.funding_rate()  # Perpetual funding rates
    """
    
    def __init__(self, symbol: str, 
                 exchange: Optional[str] = None,
                 http_proxy: Optional[str] = None, 
                 log_level: Optional[str] = logging.INFO, 
                 config: Optional[Configuration] = None):
        """
        Args:
            symbol: Token symbol (e.g., 'BTC', 'ETH', 'SOL')
            exchange: Filter to specific exchange (e.g., 'binance')
            http_proxy: HTTP proxy URL
            log_level: Logging level
            config: DuckDB configuration
        """
        self.symbol = self._normalize_symbol(symbol)
        self.exchange = exchange.lower() if exchange else None
        self.http_proxy = http_proxy
        self.config = config
        self.duckdb_client = get_duckdb_client(
            http_proxy=self.http_proxy, 
            log_level=log_level, 
            config=config
        )
        self.hf_client = HuggingFaceClient()
        self.log_level = log_level
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to standard format (e.g., BTC -> BTCUSDT)"""
        symbol = symbol.upper().replace('/', '')
        if not symbol.endswith(('USDT', 'USDC', 'USD', 'BUSD')):
            symbol = symbol + 'USDT'
        return symbol
    
    def _query_table(self, table: str, sql_template: str, **kwargs) -> pd.DataFrame:
        """Execute query against a HuggingFace table"""
        url = self.hf_client.get_url_path(table)
        sql = load_sql(sql_template, url=url, symbol=self.symbol, **kwargs)
        return self.duckdb_client.query(sql)
    
    # =========== Price Data ===========
    
    def ohlcv(self, interval: str = "1d", limit: int = 365) -> pd.DataFrame:
        """Get OHLCV candlestick data
        
        Args:
            interval: '1d' (daily) or '1h' (hourly)
            limit: Maximum number of candles to return
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        table = ohlcv_daily if interval == "1d" else ohlcv_hourly
        
        exchange_filter = f"AND exchange = '{self.exchange}'" if self.exchange else ""
        
        return self._query_table(
            table, 
            "select_ohlcv",
            exchange_filter=exchange_filter,
            limit=limit
        )
    
    def price(self) -> pd.DataFrame:
        """Get latest price data"""
        return self.ohlcv(interval="1d", limit=1)
    
    def price_history(self, days: int = 365) -> pd.DataFrame:
        """Get price history (close prices only)"""
        df = self.ohlcv(interval="1d", limit=days)
        return df[['timestamp', 'close']].rename(columns={'close': 'price'})
    
    # =========== Derivatives Data ===========
    
    def funding_rate(self, limit: int = 100) -> pd.DataFrame:
        """Get perpetual futures funding rate history
        
        Returns:
            DataFrame with columns: timestamp, funding_rate, mark_price
        """
        exchange_filter = f"AND exchange = '{self.exchange}'" if self.exchange else ""
        
        return self._query_table(
            funding_rates,
            "select_funding",
            exchange_filter=exchange_filter,
            limit=limit
        )
    
    def open_interest(self, limit: int = 100) -> pd.DataFrame:
        """Get open interest history
        
        Returns:
            DataFrame with columns: timestamp, open_interest, open_interest_value
        """
        exchange_filter = f"AND exchange = '{self.exchange}'" if self.exchange else ""
        
        return self._query_table(
            open_interest,
            "select_oi",
            exchange_filter=exchange_filter,
            limit=limit
        )
    
    def liquidations(self, days: int = 7) -> pd.DataFrame:
        """Get liquidation events
        
        Returns:
            DataFrame with columns: timestamp, side, quantity, price, value
        """
        exchange_filter = f"AND exchange = '{self.exchange}'" if self.exchange else ""
        
        return self._query_table(
            liquidations,
            "select_liquidations",
            exchange_filter=exchange_filter,
            days=days
        )
    
    # =========== Computed Metrics ===========
    
    def volatility(self, window: int = 30) -> pd.DataFrame:
        """Calculate realized volatility (annualized)
        
        Args:
            window: Rolling window in days
            
        Returns:
            DataFrame with columns: timestamp, volatility
        """
        df = self.ohlcv(interval="1d", limit=window + 100)
        
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility'] = df['log_return'].rolling(window=window).std() * np.sqrt(365)
        
        return df[['timestamp', 'volatility']].dropna()
    
    def returns(self, period: str = "1d") -> pd.DataFrame:
        """Calculate returns over various periods
        
        Args:
            period: '1d', '7d', '30d', '90d', '365d'
            
        Returns:
            DataFrame with period returns
        """
        period_days = {
            '1d': 1, '7d': 7, '30d': 30, '90d': 90, '365d': 365
        }
        
        days = period_days.get(period, 1)
        df = self.ohlcv(interval="1d", limit=days + 1)
        
        if len(df) < 2:
            return pd.DataFrame()
        
        current_price = df.iloc[-1]['close']
        past_price = df.iloc[0]['close']
        
        return pd.DataFrame([{
            'symbol': self.symbol,
            'period': period,
            'return': (current_price - past_price) / past_price,
            'current_price': current_price,
            'past_price': past_price
        }])
    
    def funding_rate_annualized(self) -> pd.DataFrame:
        """Calculate annualized funding rate
        
        Assumes 8-hour funding intervals (3x per day)
        """
        df = self.funding_rate(limit=30)
        
        df['annualized_rate'] = df['funding_rate'] * 3 * 365
        
        return df[['timestamp', 'funding_rate', 'annualized_rate']]
    
    def basis(self) -> pd.DataFrame:
        """Calculate futures basis (futures - spot) / spot
        
        Requires both spot and futures data
        """
        # Would need to query both spot and futures prices
        raise NotImplementedError("Basis calculation requires spot/futures price comparison")
    
    # =========== Token Info ===========
    
    def info(self) -> pd.DataFrame:
        """Get token metadata (name, category, market cap, etc.)"""
        return self._query_table(token_info, "select_token_info")
    
    def market_cap(self) -> pd.DataFrame:
        """Get market capitalization history"""
        info = self.info()
        price_history = self.price_history()
        
        if 'circulating_supply' not in info.columns:
            raise ValueError("Circulating supply not available")
        
        supply = info['circulating_supply'].iloc[0]
        price_history['market_cap'] = price_history['price'] * supply
        
        return price_history[['timestamp', 'price', 'market_cap']]
    
    # =========== Reports ===========
    
    def tearsheet(self, output: str = None):
        """Generate HTML tearsheet report
        
        Args:
            output: Output file path (default: {symbol}_report.html)
        """
        from defeatbeta_crypto.reports import tearsheet
        tearsheet.html(self, output=output or f"{self.symbol}_report.html")
```

## SQL Templates

### select_ohlcv.sql

```sql
SELECT 
    timestamp,
    symbol,
    exchange,
    open,
    high,
    low,
    close,
    volume,
    quote_volume,
    trades_count
FROM '{url}'
WHERE symbol = '{symbol}'
    {exchange_filter}
ORDER BY timestamp DESC
LIMIT {limit}
```

### select_funding.sql

```sql
SELECT 
    timestamp,
    symbol,
    exchange,
    funding_rate,
    funding_interval_hours,
    mark_price,
    index_price
FROM '{url}'
WHERE symbol = '{symbol}'
    {exchange_filter}
ORDER BY timestamp DESC
LIMIT {limit}
```

### select_oi.sql

```sql
SELECT 
    timestamp,
    symbol,
    exchange,
    open_interest,
    open_interest_value
FROM '{url}'
WHERE symbol = '{symbol}'
    {exchange_filter}
ORDER BY timestamp DESC
LIMIT {limit}
```

## Constants

```python
# defeatbeta_crypto/utils/const.py

# Table names
ohlcv_daily = "ohlcv_daily"
ohlcv_hourly = "ohlcv_hourly"
ohlcv_1m = "ohlcv_1m"
funding_rates = "funding_rates"
open_interest = "open_interest"
liquidations = "liquidations"
token_info = "token_info"
exchange_info = "exchange_info"

TABLES = [
    ohlcv_daily, ohlcv_hourly, ohlcv_1m,
    funding_rates, open_interest, liquidations,
    token_info, exchange_info
]

# Supported exchanges
EXCHANGES = ["binance", "coinbase", "okx", "bybit"]

# Common trading pairs
TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"
]
```

## Usage Examples

### Basic Usage

```python
from defeatbeta_crypto import Token

# Initialize token
btc = Token("BTC")

# Get daily OHLCV
ohlcv = btc.ohlcv(interval="1d", limit=365)
print(ohlcv.head())

# Get funding rates
funding = btc.funding_rate(limit=30)
print(funding.head())

# Calculate volatility
vol = btc.volatility(window=30)
print(vol.tail())
```

### Exchange-Specific Data

```python
# Get Binance-only data
btc_binance = Token("BTC", exchange="binance")
ohlcv = btc_binance.ohlcv()

# Compare across exchanges
for exchange in ["binance", "coinbase", "okx"]:
    token = Token("BTC", exchange=exchange)
    df = token.ohlcv(limit=1)
    print(f"{exchange}: {df['close'].iloc[0]}")
```

### Multiple Tokens

```python
from defeatbeta_crypto import Token

symbols = ["BTC", "ETH", "SOL", "AVAX"]

for symbol in symbols:
    token = Token(symbol)
    returns = token.returns(period="30d")
    print(f"{symbol}: {returns['return'].iloc[0]:.2%}")
```

### Generate Reports

```python
from defeatbeta_crypto import Token

btc = Token("BTC")
btc.tearsheet(output="btc_analysis.html")
```

## Dependencies

```toml
[project]
name = "defeatbeta-crypto-api"
version = "0.1.0"
description = "Cryptocurrency market data API powered by DuckDB"
requires-python = ">=3.9"
dependencies = [
    "duckdb >= 1.4.1",
    "pandas >= 2.2.3",
    "requests >= 2.32.3",
    "tabulate >= 0.9.0",
    "numpy >= 2.2.5",
    "matplotlib >= 3.10.0",
    "pyfiglet >= 1.0.2",
]

[project.optional-dependencies]
dev = [
    "pytest >= 8.0.0",
    "pytest-cov >= 4.0.0",
]
```

---

## Template Definitions

### token_categories.json

Token categorization for filtering and grouping by market sector.

```json
{
  "version": "1.0.0",
  "updated_at": "2024-01-01T00:00:00Z",
  "categories": {
    "layer1": {
      "name": "Layer 1",
      "description": "Base layer blockchain protocols",
      "symbols": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT",
        "ADAUSDT", "NEARUSDT", "ATOMUSDT", "APTUSDT", "SUIUSDT"
      ]
    },
    "layer2": {
      "name": "Layer 2",
      "description": "Scaling solutions built on Layer 1",
      "symbols": [
        "MATICUSDT", "ARBUSDT", "OPUSDT", "IMXUSDT", "METISUSDT",
        "ZKUSDT", "MANTAUSDT", "STRKUSDT"
      ]
    },
    "defi": {
      "name": "DeFi",
      "description": "Decentralized finance protocols",
      "symbols": [
        "UNIUSDT", "AAVEUSDT", "MKRUSDT", "COMPUSDT", "CRVUSDT",
        "SNXUSDT", "YFIUSDT", "SUSHIUSDT", "1INCHUSDT", "LDOUSDT"
      ]
    },
    "exchange": {
      "name": "Exchange Tokens",
      "description": "Centralized and decentralized exchange tokens",
      "symbols": [
        "BNBUSDT", "FTMUSDT", "OKBUSDT", "HTUSDT", "KCSUSDT",
        "CRONUSDT", "GTUSDT"
      ]
    },
    "meme": {
      "name": "Meme Coins",
      "description": "Community-driven meme tokens",
      "symbols": [
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT",
        "WIFUSDT", "MEMEUSDT"
      ]
    },
    "gaming": {
      "name": "Gaming & Metaverse",
      "description": "Gaming and virtual world tokens",
      "symbols": [
        "AXSUSDT", "SANDUSDT", "MANAUSDT", "ENJUSDT", "GALAUSDT",
        "IMXUSDT", "YGGUSDT", "MAGICUSDT"
      ]
    },
    "infrastructure": {
      "name": "Infrastructure",
      "description": "Blockchain infrastructure and oracle services",
      "symbols": [
        "LINKUSDT", "FILUSDT", "GRTUSDT", "ARUSDT", "OCEANUSDT",
        "RNDRSUDT", "THETAUSDT"
      ]
    },
    "stablecoin": {
      "name": "Stablecoins",
      "description": "Price-stable cryptocurrencies (for reference)",
      "symbols": [
        "USDTUSDC", "DAIUSDT", "FRAXUSDT", "LUSDUSDT", "TUSDUSDT"
      ]
    },
    "ai": {
      "name": "AI & Machine Learning",
      "description": "AI-focused blockchain projects",
      "symbols": [
        "FETUSDT", "AGIXUSDT", "OCEANUSDT", "RNDRSUDT", "TAOUSDT",
        "ARKMUSDT", "WLDUSDT"
      ]
    },
    "privacy": {
      "name": "Privacy Coins",
      "description": "Privacy-focused cryptocurrencies",
      "symbols": [
        "XMRUSDT", "ZECUSDT", "DASHUSDT", "SCRTUSDT"
      ]
    }
  },
  "symbol_to_category": {
    "BTCUSDT": ["layer1"],
    "ETHUSDT": ["layer1", "defi"],
    "SOLUSDT": ["layer1"],
    "BNBUSDT": ["layer1", "exchange"],
    "XRPUSDT": ["layer1"],
    "ADAUSDT": ["layer1"],
    "DOGEUSDT": ["meme"],
    "AVAXUSDT": ["layer1"],
    "DOTUSDT": ["layer1"],
    "MATICUSDT": ["layer2"],
    "LINKUSDT": ["infrastructure"],
    "UNIUSDT": ["defi"],
    "AAVEUSDT": ["defi"],
    "ARBUSDT": ["layer2"],
    "OPUSDT": ["layer2"],
    "SHIBUSDT": ["meme"],
    "PEPEUSDT": ["meme"],
    "FETUSDT": ["ai"],
    "RNDRSUDT": ["ai", "infrastructure"]
  }
}
```

### exchange_symbols.json

Mapping of normalized symbols to exchange-specific formats.

```json
{
  "version": "1.0.0",
  "updated_at": "2024-01-01T00:00:00Z",
  "exchanges": {
    "binance": {
      "name": "Binance",
      "base_url": "https://api.binance.com",
      "symbol_format": "{base}{quote}",
      "default_quote": "USDT",
      "symbols": {
        "BTCUSDT": {
          "native_symbol": "BTCUSDT",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active",
          "min_notional": 10.0,
          "tick_size": 0.01,
          "lot_size": 0.00001
        },
        "ETHUSDT": {
          "native_symbol": "ETHUSDT",
          "base": "ETH",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active",
          "min_notional": 10.0,
          "tick_size": 0.01,
          "lot_size": 0.0001
        },
        "SOLUSDT": {
          "native_symbol": "SOLUSDT",
          "base": "SOL",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active"
        }
      },
      "perpetuals": {
        "BTCUSDT": {
          "native_symbol": "BTCUSDT",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "perpetual",
          "funding_interval_hours": 8,
          "status": "active"
        },
        "ETHUSDT": {
          "native_symbol": "ETHUSDT",
          "base": "ETH",
          "quote": "USDT",
          "contract_type": "perpetual",
          "funding_interval_hours": 8,
          "status": "active"
        }
      }
    },
    "coinbase": {
      "name": "Coinbase",
      "base_url": "https://api.exchange.coinbase.com",
      "symbol_format": "{base}-{quote}",
      "default_quote": "USD",
      "symbols": {
        "BTCUSDT": {
          "native_symbol": "BTC-USD",
          "base": "BTC",
          "quote": "USD",
          "contract_type": "spot",
          "status": "active"
        },
        "ETHUSDT": {
          "native_symbol": "ETH-USD",
          "base": "ETH",
          "quote": "USD",
          "contract_type": "spot",
          "status": "active"
        },
        "SOLUSDT": {
          "native_symbol": "SOL-USD",
          "base": "SOL",
          "quote": "USD",
          "contract_type": "spot",
          "status": "active"
        }
      }
    },
    "okx": {
      "name": "OKX",
      "base_url": "https://www.okx.com",
      "symbol_format": "{base}-{quote}",
      "default_quote": "USDT",
      "symbols": {
        "BTCUSDT": {
          "native_symbol": "BTC-USDT",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active"
        },
        "ETHUSDT": {
          "native_symbol": "ETH-USDT",
          "base": "ETH",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active"
        }
      },
      "perpetuals": {
        "BTCUSDT": {
          "native_symbol": "BTC-USDT-SWAP",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "perpetual",
          "funding_interval_hours": 8,
          "status": "active"
        }
      }
    },
    "bybit": {
      "name": "Bybit",
      "base_url": "https://api.bybit.com",
      "symbol_format": "{base}{quote}",
      "default_quote": "USDT",
      "symbols": {
        "BTCUSDT": {
          "native_symbol": "BTCUSDT",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active"
        },
        "ETHUSDT": {
          "native_symbol": "ETHUSDT",
          "base": "ETH",
          "quote": "USDT",
          "contract_type": "spot",
          "status": "active"
        }
      },
      "perpetuals": {
        "BTCUSDT": {
          "native_symbol": "BTCUSDT",
          "base": "BTC",
          "quote": "USDT",
          "contract_type": "perpetual",
          "funding_interval_hours": 8,
          "status": "active"
        }
      }
    }
  },
  "normalized_symbols": [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "UNIUSDT", "AAVEUSDT", "ARBUSDT", "OPUSDT",
    "SHIBUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "NEARUSDT"
  ],
  "delisted": {
    "LUNAUSDT": {
      "delisted_at": "2022-05-13",
      "reason": "Terra collapse",
      "exchanges": ["binance", "coinbase", "okx"]
    },
    "FTXUSDT": {
      "delisted_at": "2022-11-11",
      "reason": "FTX bankruptcy",
      "exchanges": ["binance"]
    }
  }
}
```

### Template Loader

```python
# defeatbeta_crypto/data/template/loader.py

import json
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache


TEMPLATE_DIR = Path(__file__).parent


@lru_cache(maxsize=2)
def load_token_categories() -> Dict:
    """Load token categories template."""
    path = TEMPLATE_DIR / "token_categories.json"
    with open(path) as f:
        return json.load(f)


@lru_cache(maxsize=2)
def load_exchange_symbols() -> Dict:
    """Load exchange symbols template."""
    path = TEMPLATE_DIR / "exchange_symbols.json"
    with open(path) as f:
        return json.load(f)


def get_symbols_by_category(category: str) -> List[str]:
    """Get all symbols in a category."""
    data = load_token_categories()
    cat = data["categories"].get(category)
    if not cat:
        raise ValueError(f"Unknown category: {category}")
    return cat["symbols"]


def get_category_for_symbol(symbol: str) -> List[str]:
    """Get categories for a symbol."""
    data = load_token_categories()
    return data["symbol_to_category"].get(symbol, [])


def get_native_symbol(normalized: str, exchange: str) -> Optional[str]:
    """Convert normalized symbol to exchange-native format."""
    data = load_exchange_symbols()
    exchange_data = data["exchanges"].get(exchange)
    if not exchange_data:
        raise ValueError(f"Unknown exchange: {exchange}")
    
    symbol_data = exchange_data["symbols"].get(normalized)
    if symbol_data:
        return symbol_data["native_symbol"]
    
    # Check perpetuals
    perps = exchange_data.get("perpetuals", {})
    perp_data = perps.get(normalized)
    if perp_data:
        return perp_data["native_symbol"]
    
    return None


def get_normalized_symbol(native: str, exchange: str) -> Optional[str]:
    """Convert exchange-native symbol to normalized format."""
    data = load_exchange_symbols()
    exchange_data = data["exchanges"].get(exchange)
    if not exchange_data:
        return None
    
    # Search in spot symbols
    for norm, sym_data in exchange_data["symbols"].items():
        if sym_data["native_symbol"] == native:
            return norm
    
    # Search in perpetuals
    for norm, sym_data in exchange_data.get("perpetuals", {}).items():
        if sym_data["native_symbol"] == native:
            return norm
    
    return None


def is_delisted(symbol: str) -> bool:
    """Check if a symbol has been delisted."""
    data = load_exchange_symbols()
    return symbol in data.get("delisted", {})


def get_all_normalized_symbols() -> List[str]:
    """Get list of all normalized symbols."""
    data = load_exchange_symbols()
    return data["normalized_symbols"]
```

### Usage with Templates

```python
from defeatbeta_crypto import Token
from defeatbeta_crypto.data.template.loader import (
    get_symbols_by_category,
    get_native_symbol,
    get_category_for_symbol,
)

# Get all DeFi tokens
defi_symbols = get_symbols_by_category("defi")
for symbol in defi_symbols[:5]:
    token = Token(symbol)
    print(f"{symbol}: {token.price()['close'].iloc[0]}")

# Check symbol categories
categories = get_category_for_symbol("ETHUSDT")
print(f"ETH categories: {categories}")  # ['layer1', 'defi']

# Get native symbol for exchange
native = get_native_symbol("BTCUSDT", "coinbase")
print(f"Coinbase native: {native}")  # BTC-USD
```
