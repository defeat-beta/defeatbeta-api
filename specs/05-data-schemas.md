# 05 - Data Schemas

> Parquet schemas, SQL templates, and data dictionary

## Parquet Schemas (PyArrow)

### OHLCV Schema

```python
import pyarrow as pa

OHLCV_SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('us', tz='UTC')),
    ('symbol', pa.string()),
    ('exchange', pa.string()),
    ('open', pa.float64()),
    ('high', pa.float64()),
    ('low', pa.float64()),
    ('close', pa.float64()),
    ('volume', pa.float64()),
    ('quote_volume', pa.float64()),
    ('trades_count', pa.int64()),
])
```

| Column | Type | Description |
|--------|------|-------------|
| timestamp | timestamp[us, UTC] | Candle open time |
| symbol | string | Trading pair (e.g., BTCUSDT) |
| exchange | string | Exchange name (binance, coinbase, etc.) |
| open | float64 | Opening price |
| high | float64 | Highest price in period |
| low | float64 | Lowest price in period |
| close | float64 | Closing price |
| volume | float64 | Base asset volume |
| quote_volume | float64 | Quote asset volume (USD value) |
| trades_count | int64 | Number of trades in period |

### Funding Rate Schema

```python
FUNDING_RATE_SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('us', tz='UTC')),
    ('symbol', pa.string()),
    ('exchange', pa.string()),
    ('funding_rate', pa.float64()),
    ('funding_interval_hours', pa.int32()),
    ('mark_price', pa.float64()),
    ('index_price', pa.float64()),
])
```

| Column | Type | Description |
|--------|------|-------------|
| timestamp | timestamp[us, UTC] | Funding settlement time |
| symbol | string | Perpetual contract symbol |
| exchange | string | Exchange name |
| funding_rate | float64 | Funding rate (e.g., 0.0001 = 0.01%) |
| funding_interval_hours | int32 | Hours between settlements (usually 8) |
| mark_price | float64 | Mark price at settlement |
| index_price | float64 | Index (spot) price at settlement |

### Open Interest Schema

```python
OPEN_INTEREST_SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('us', tz='UTC')),
    ('symbol', pa.string()),
    ('exchange', pa.string()),
    ('open_interest', pa.float64()),
    ('open_interest_value', pa.float64()),
])
```

| Column | Type | Description |
|--------|------|-------------|
| timestamp | timestamp[us, UTC] | Snapshot time |
| symbol | string | Contract symbol |
| exchange | string | Exchange name |
| open_interest | float64 | Open interest in contracts/coins |
| open_interest_value | float64 | Open interest in USD |

### Liquidation Schema

```python
LIQUIDATION_SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('us', tz='UTC')),
    ('symbol', pa.string()),
    ('exchange', pa.string()),
    ('side', pa.string()),
    ('quantity', pa.float64()),
    ('price', pa.float64()),
    ('value', pa.float64()),
])
```

| Column | Type | Description |
|--------|------|-------------|
| timestamp | timestamp[us, UTC] | Liquidation time |
| symbol | string | Contract symbol |
| exchange | string | Exchange name |
| side | string | 'long' or 'short' |
| quantity | float64 | Liquidated quantity |
| price | float64 | Liquidation price |
| value | float64 | Liquidation value in USD |

### Token Info Schema

```python
TOKEN_INFO_SCHEMA = pa.schema([
    ('symbol', pa.string()),
    ('name', pa.string()),
    ('category', pa.string()),
    ('market_cap', pa.float64()),
    ('market_cap_rank', pa.int32()),
    ('circulating_supply', pa.float64()),
    ('total_supply', pa.float64()),
    ('max_supply', pa.float64()),
    ('coingecko_id', pa.string()),
    ('website', pa.string()),
    ('description', pa.string()),
    ('updated_at', pa.timestamp('us', tz='UTC')),
])
```

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | Token symbol (e.g., BTC) |
| name | string | Full name (e.g., Bitcoin) |
| category | string | Category (e.g., layer-1, defi, meme) |
| market_cap | float64 | Market capitalization in USD |
| market_cap_rank | int32 | Rank by market cap |
| circulating_supply | float64 | Circulating token supply |
| total_supply | float64 | Total token supply |
| max_supply | float64 | Maximum supply (null if unlimited) |
| coingecko_id | string | CoinGecko identifier |
| website | string | Project website |
| description | string | Project description |
| updated_at | timestamp | Last update time |

### Exchange Info Schema

```python
EXCHANGE_INFO_SCHEMA = pa.schema([
    ('exchange', pa.string()),
    ('symbol', pa.string()),
    ('base_asset', pa.string()),
    ('quote_asset', pa.string()),
    ('is_spot', pa.bool_()),
    ('is_futures', pa.bool_()),
    ('is_margin', pa.bool_()),
    ('status', pa.string()),
    ('min_quantity', pa.float64()),
    ('max_quantity', pa.float64()),
    ('tick_size', pa.float64()),
    ('updated_at', pa.timestamp('us', tz='UTC')),
])
```

## SQL Query Templates

### select_ohlcv.sql

```sql
-- Select OHLCV data for a symbol
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

### select_ohlcv_date_range.sql

```sql
-- Select OHLCV data within date range
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
    AND timestamp >= '{start_date}'
    AND timestamp <= '{end_date}'
    {exchange_filter}
ORDER BY timestamp ASC
```

### select_funding.sql

```sql
-- Select funding rate history
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

### select_funding_aggregated.sql

```sql
-- Aggregate funding rate across exchanges
SELECT 
    timestamp,
    symbol,
    AVG(funding_rate) as avg_funding_rate,
    MIN(funding_rate) as min_funding_rate,
    MAX(funding_rate) as max_funding_rate,
    COUNT(DISTINCT exchange) as exchange_count
FROM '{url}'
WHERE symbol = '{symbol}'
GROUP BY timestamp, symbol
ORDER BY timestamp DESC
LIMIT {limit}
```

### select_oi.sql

```sql
-- Select open interest
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

### select_oi_total.sql

```sql
-- Total open interest across exchanges
SELECT 
    timestamp,
    symbol,
    SUM(open_interest) as total_open_interest,
    SUM(open_interest_value) as total_open_interest_value
FROM '{url}'
WHERE symbol = '{symbol}'
GROUP BY timestamp, symbol
ORDER BY timestamp DESC
LIMIT {limit}
```

### select_liquidations.sql

```sql
-- Select liquidation events
SELECT 
    timestamp,
    symbol,
    exchange,
    side,
    quantity,
    price,
    value
FROM '{url}'
WHERE symbol = '{symbol}'
    AND timestamp >= NOW() - INTERVAL '{days} days'
    {exchange_filter}
ORDER BY timestamp DESC
```

### select_liquidations_summary.sql

```sql
-- Summarize liquidations by day and side
SELECT 
    DATE_TRUNC('day', timestamp) as date,
    symbol,
    side,
    COUNT(*) as liquidation_count,
    SUM(value) as total_value,
    AVG(value) as avg_value
FROM '{url}'
WHERE symbol = '{symbol}'
    AND timestamp >= NOW() - INTERVAL '{days} days'
GROUP BY DATE_TRUNC('day', timestamp), symbol, side
ORDER BY date DESC, side
```

### select_token_info.sql

```sql
-- Select token metadata
SELECT 
    symbol,
    name,
    category,
    market_cap,
    market_cap_rank,
    circulating_supply,
    total_supply,
    max_supply,
    coingecko_id,
    website,
    description
FROM '{url}'
WHERE symbol = '{symbol}'
```

### select_volatility.sql

```sql
-- Calculate rolling volatility
WITH price_data AS (
    SELECT 
        timestamp,
        close,
        LN(close / LAG(close) OVER (ORDER BY timestamp)) as log_return
    FROM '{url}'
    WHERE symbol = '{symbol}'
        {exchange_filter}
    ORDER BY timestamp DESC
    LIMIT {window} + 100
)
SELECT 
    timestamp,
    close,
    log_return,
    STDDEV(log_return) OVER (
        ORDER BY timestamp 
        ROWS BETWEEN {window} - 1 PRECEDING AND CURRENT ROW
    ) * SQRT(365) as volatility
FROM price_data
WHERE log_return IS NOT NULL
ORDER BY timestamp DESC
LIMIT {limit}
```

### select_returns.sql

```sql
-- Calculate returns over period
WITH current_price AS (
    SELECT close 
    FROM '{url}'
    WHERE symbol = '{symbol}'
    ORDER BY timestamp DESC
    LIMIT 1
),
past_price AS (
    SELECT close
    FROM '{url}'
    WHERE symbol = '{symbol}'
    ORDER BY timestamp DESC
    OFFSET {days}
    LIMIT 1
)
SELECT 
    '{symbol}' as symbol,
    '{period}' as period,
    (c.close - p.close) / p.close as return_pct,
    c.close as current_price,
    p.close as past_price
FROM current_price c, past_price p
```

### select_market_dominance.sql

```sql
-- Calculate market dominance
WITH total_market AS (
    SELECT SUM(market_cap) as total_cap
    FROM '{token_info_url}'
    WHERE market_cap IS NOT NULL
),
token_cap AS (
    SELECT market_cap
    FROM '{token_info_url}'
    WHERE symbol = '{symbol}'
)
SELECT 
    '{symbol}' as symbol,
    t.market_cap,
    m.total_cap as total_market_cap,
    t.market_cap / m.total_cap as dominance
FROM token_cap t, total_market m
```

## Data Dictionary

### Symbol Naming Convention

| Exchange | Format | Example |
|----------|--------|---------|
| Binance | BASEUSDT | BTCUSDT |
| Coinbase | BASE-USD | BTC-USD |
| OKX | BASE-USDT | BTC-USDT |
| Normalized | BASEUSDT | BTCUSDT |

**Normalization Rules:**
- Remove hyphens and slashes
- Uppercase all characters
- Append USDT if no quote asset specified

### Exchange Identifiers

| Identifier | Full Name | API Type |
|------------|-----------|----------|
| binance | Binance | REST + WebSocket |
| coinbase | Coinbase Pro | REST |
| okx | OKX | REST + WebSocket |
| bybit | Bybit | REST + WebSocket |
| aggregated | Cross-exchange average | Computed |

### Token Categories

| Category | Description | Examples |
|----------|-------------|----------|
| layer-1 | Base layer blockchains | BTC, ETH, SOL |
| layer-2 | Scaling solutions | MATIC, ARB, OP |
| defi | DeFi protocols | UNI, AAVE, MKR |
| meme | Meme tokens | DOGE, SHIB, PEPE |
| exchange | Exchange tokens | BNB, FTT, CRO |
| stablecoin | Stablecoins | USDT, USDC, DAI |
| infrastructure | Infrastructure | LINK, GRT, FIL |

### Time Intervals

| Interval | Table | Update Frequency |
|----------|-------|------------------|
| 1m | ohlcv_1m | Every minute |
| 1h | ohlcv_hourly | Every hour |
| 1d | ohlcv_daily | Daily |
| 8h | funding_rates | Every 8 hours |

### Null Value Handling

| Field | Null Meaning |
|-------|--------------|
| quote_volume | Not provided by exchange |
| trades_count | Not provided by exchange |
| max_supply | Unlimited supply |
| index_price | Not available |

## Schema Registry

```python
# defeatbeta_crypto/storage/schema.py

import pyarrow as pa
from typing import Dict

SCHEMAS: Dict[str, pa.Schema] = {
    'ohlcv_daily': OHLCV_SCHEMA,
    'ohlcv_hourly': OHLCV_SCHEMA,
    'ohlcv_1m': OHLCV_SCHEMA,
    'funding_rates': FUNDING_RATE_SCHEMA,
    'open_interest': OPEN_INTEREST_SCHEMA,
    'liquidations': LIQUIDATION_SCHEMA,
    'token_info': TOKEN_INFO_SCHEMA,
    'exchange_info': EXCHANGE_INFO_SCHEMA,
}

def get_schema(table_name: str) -> pa.Schema:
    """Get PyArrow schema for a table"""
    if table_name not in SCHEMAS:
        raise ValueError(f"Unknown table: {table_name}")
    return SCHEMAS[table_name]

def validate_dataframe(df: pd.DataFrame, table_name: str) -> bool:
    """Validate DataFrame against expected schema"""
    schema = get_schema(table_name)
    expected_columns = set(field.name for field in schema)
    actual_columns = set(df.columns)
    
    missing = expected_columns - actual_columns
    extra = actual_columns - expected_columns
    
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    if extra:
        # Extra columns are warnings, not errors
        import warnings
        warnings.warn(f"Extra columns will be ignored: {extra}")
    
    return True
```
