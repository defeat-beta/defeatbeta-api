# DefeatBeta API Reference

Comprehensive reference for all 60+ defeatbeta-api endpoints.

## Data Cutoff & Reference Date

### get_latest_data_update_date()
**Returns**: Dictionary with latest data update date
```python
{
    "latest_data_update_date": "2025-01-24"  # YYYY-MM-DD format
}
```
**Usage**: Always call first. Use this date as "today" for relative time queries.

## Market & Macro Data

### get_sp500_historical_annual_returns()
**Returns**: S&P 500 annual returns since 1928
```python
{
    "date_range": "1928 to 2024",
    "rows_returned": 97,
    "data": [
        {
            "year": 2024,
            "annual_return": 0.2345  # 23.45% return
        }
    ]
}
```

### get_sp500_cagr_returns(years: int)
**Parameters**:
- `years`: Number of recent years (e.g., 10 for 10-year CAGR)

**Returns**: CAGR for specified period
```python
{
    "years": 10,
    "cagr_returns": 0.1107  # 11.07% annualized
}
```

### get_sp500_cagr_returns_rolling(years: int)
**Parameters**:
- `years`: Rolling window size (e.g., 10 for all 10-year periods)

**Returns**: All possible N-year rolling CAGRs
```python
{
    "years": 10,
    "rows_returned": 88,
    "data": [
        {
            "start_year": 1928,
            "end_year": 1937,
            "cagr_returns": -0.0123
        }
    ]
}
```

### get_daily_treasury_yield()
**Returns**: Daily Treasury yield curve (all maturities)
```python
{
    "date_range": "1990-01-02 to 2025-01-24",
    "rows_returned": 8832,
    "data": [
        {
            "report_date": "2025-01-24",
            "bc1_month": 0.0422,   # 4.22%
            "bc3_month": 0.0435,
            "bc6_month": 0.0441,
            "bc1_year": 0.0448,
            "bc2_year": 0.0437,
            "bc3_year": 0.0430,
            "bc5_year": 0.0425,
            "bc7_year": 0.0427,
            "bc10_year": 0.0433,
            "bc30_year": 0.0461
        }
    ]
}
```

## Company Information APIs

### get_stock_profile(symbol: str)
**Parameters**:
- `symbol`: Stock ticker (e.g., "TSLA")

**Returns**: Company profile information
```python
{
    "symbol": "TSLA",
    "address": "1 Tesla Road",
    "city": "Austin",
    "country": "United States",
    "phone": "512 516 8177",
    "zip": "78725",
    "industry": "Auto Manufacturers",
    "sector": "Consumer Cyclical",
    "long_business_summary": "Tesla, Inc. designs, develops...",
    "full_time_employees": 125665,
    "web_site": "https://www.tesla.com",
    "report_date": "2025-01-24"
}
```

### get_stock_officers(symbol: str)
**Returns**: Executive team with compensation
```python
{
    "symbol": "TSLA",
    "rows_returned": 10,
    "officers": [
        {
            "name": "Mr. Elon R. Musk",
            "title": "Technoking of Tesla, CEO & Director",
            "age": 53,
            "born": 1971,
            "pay": 0,  # in USD, null if not disclosed
            "exercised": 0,  # stock options exercised
            "unexercised": 0  # stock options unexercised
        }
    ]
}
```

### get_stock_sec_filings(symbol: str, start_date: str = None, end_date: str = None)
**Parameters**:
- `symbol`: Stock ticker
- `start_date`: Optional "YYYY-MM-DD"
- `end_date`: Optional "YYYY-MM-DD"
- **MAX 500 rows** (truncated if exceeded)

**Returns**: SEC filing history
```python
{
    "symbol": "TSLA",
    "date_range": "2010-02-01 to 2025-01-24",
    "rows_returned": 500,
    "truncated": false,
    "sec_user_agent": "DefeatBeta contact@defeatbeta.com",
    "sec_access_note": "Use this User-Agent header to access filing_url",
    "filings": [
        {
            "form_type": "10-K",
            "filing_date": "2024-01-29",
            "report_date": "2023-12-31",
            "acceptance_date_time": "2024-01-29T16:05:02.000Z",
            "cik": "0001318605",
            "accession_number": "0001628280-24-002390",
            "company_name": "Tesla, Inc.",
            "filing_url": "https://www.sec.gov/Archives/edgar/data/..."
        }
    ]
}
```

**Form Types**:
- US Companies: 10-K, 10-Q, 8-K, DEF 14A
- Insider Trading: 3, 4, 5, 144
- Institutional Holdings: 13F-HR, SC 13G, SC 13D
- Foreign Issuers: 20-F, 6-K
- Canadian: 40-F
- ETFs: N-CSR, NPORT-P

### get_stock_earning_call_transcripts_list(symbol: str)
**Returns**: Available earnings call metadata
```python
{
    "symbol": "TSLA",
    "rows_returned": 25,
    "transcripts": [
        {
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "report_date": "2025-01-29"
        }
    ]
}
```

### get_stock_earning_call_transcript(symbol: str, fiscal_year: int, fiscal_quarter: int)
**Parameters**:
- `fiscal_year`: Fiscal year (e.g., 2024)
- `fiscal_quarter`: 1-4

**Returns**: Full earnings call transcript
```python
{
    "symbol": "TSLA",
    "fiscal_year": 2024,
    "fiscal_quarter": 4,
    "paragraphs": [
        {
            "paragraph_number": 1,
            "speaker": "Operator",
            "content": "Good afternoon, everyone..."
        }
    ]
}
```

### get_stock_news(symbol: str, start_date: str = None, end_date: str = None, max_rows: int = 50)
**Parameters**:
- `max_rows`: Default 50 (configurable to avoid token limits)

**Returns**: News articles with full content
```python
{
    "symbol": "TSLA",
    "date_range": "2024-01-01 to 2025-01-24",
    "rows_returned": 50,
    "truncated": false,
    "news": [
        {
            "uuid": "abc-123",
            "report_date": "2025-01-24",
            "title": "Tesla Announces...",
            "publisher": "Bloomberg",
            "type": "STORY",
            "link": "https://...",
            "related_symbols": ["TSLA"],
            "paragraphs": [
                {
                    "paragraph_number": 1,
                    "paragraph": "Tesla Inc. announced...",
                    "highlight": "key quote"  # optional
                }
            ]
        }
    ]
}
```

## Price & Market Data

### get_stock_price(symbol: str, start_date: str = None, end_date: str = None)
**Parameters**:
- **MAX 1000 rows** (most recent if truncated)

**Returns**: Historical OHLCV data
```python
{
    "symbol": "TSLA",
    "date_range": "2015-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "latest_close": 234.56,
    "data": [
        {
            "report_date": "2025-01-24",
            "open": 230.00,
            "high": 235.00,
            "low": 228.00,
            "close": 234.56,
            "volume": 98765432,
            "adj_close": 234.56
        }
    ]
}
```

### get_stock_market_capitalization(symbol: str, start_date: str = None, end_date: str = None)
**Parameters**:
- **MAX 1000 rows** (most recent if truncated)

**Returns**: Historical market cap
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "shares_report_date": "2024-12-31",
            "close_price": 234.56,
            "shares_outstanding": 3200000000,
            "market_capitalization": 750592000000  # in USD
        }
    ]
}
```

### get_stock_eps_and_ttm_eps(symbol: str)
**Returns**: Quarterly EPS and TTM EPS
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "rows_returned": 40,
    "data": [
        {
            "report_date": "2024-12-31",
            "eps": 0.73,  # quarterly EPS
            "ttm_eps": 3.64  # trailing 12 months EPS
        }
    ]
}
```

## Financial Statements

### Income Statement

#### get_stock_quarterly_income_statement(symbol: str)
#### get_stock_annual_income_statement(symbol: str)

**Returns**: Complete income statement
```python
{
    "currency": "USD",
    "period_type": "quarterly",  # or "annual"
    "periods": ["2024-12-31", "2024-09-30", ...],
    "rows_returned": 20,
    "statement": [
        {
            "period": "2024-12-31",
            "items": {
                "total_revenue": 25167000000,
                "cost_of_revenue": 18636000000,
                "gross_profit": 6531000000,
                "operating_expense": 2939000000,
                "operating_income": 3592000000,
                "net_income": 2321000000,
                "diluted_eps": 0.73,
                "ebitda": 4200000000,
                # ... 50+ more line items
            }
        }
    ]
}
```

### Balance Sheet

#### get_stock_quarterly_balance_sheet(symbol: str)
#### get_stock_annual_balance_sheet(symbol: str)

**Returns**: Complete balance sheet
```python
{
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "statement": [
        {
            "period": "2024-12-31",
            "items": {
                "total_assets": 123456789000,
                "current_assets": 45678900000,
                "cash_and_cash_equivalents": 12345678000,
                "total_liabilities": 67890123000,
                "stockholders_equity": 55566666000,
                # ... 40+ more line items
            }
        }
    ]
}
```

### Cash Flow Statement

#### get_stock_quarterly_cash_flow(symbol: str)
#### get_stock_annual_cash_flow(symbol: str)

**Returns**: Complete cash flow statement
```python
{
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "statement": [
        {
            "period": "2024-12-31",
            "items": {
                "operating_cash_flow": 3500000000,
                "investing_cash_flow": -2100000000,
                "financing_cash_flow": -800000000,
                "free_cash_flow": 1400000000,
                "capital_expenditure": -2100000000,
                # ... 30+ more line items
            }
        }
    ]
}
```

## Segment Analysis

### get_quarterly_revenue_by_segment(symbol: str)
**Returns**: Revenue breakdown by business segment
```python
{
    "symbol": "TSLA",
    "period_type": "quarterly",
    "periods": ["2024-12-31", ...],
    "segments": ["Automotive", "Energy Storage", "Services"],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "revenue": {
                "Automotive": 21000000000,
                "Energy Storage": 2800000000,
                "Services": 1367000000
            },
            "currency": "usd"
        }
    ]
}
```

### get_quarterly_revenue_by_geography(symbol: str)
**Returns**: Revenue breakdown by region
```python
{
    "symbol": "TSLA",
    "period_type": "quarterly",
    "periods": [...],
    "regions": ["United States", "China", "Other"],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "revenue": {
                "United States": 12000000000,
                "China": 8000000000,
                "Other": 5167000000
            },
            "currency": "usd"
        }
    ]
}
```

## Profitability Margins

All margin APIs return similar structure. Using gross margin as example:

### Quarterly Margins
- `get_stock_quarterly_gross_margin(symbol)`
- `get_stock_quarterly_operating_margin(symbol)`
- `get_stock_quarterly_net_margin(symbol)`
- `get_stock_quarterly_ebitda_margin(symbol)`
- `get_stock_quarterly_fcf_margin(symbol)`

### Annual Margins
- `get_stock_annual_gross_margin(symbol)`
- `get_stock_annual_operating_margin(symbol)`
- `get_stock_annual_net_margin(symbol)`
- `get_stock_annual_ebitda_margin(symbol)`
- `get_stock_annual_fcf_margin(symbol)`

**Returns**:
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "gross_profit": 6531000000,
            "total_revenue": 25167000000,
            "gross_margin": 0.2595  # 25.95%
        }
    ]
}
```

## Profitability Ratios

### get_stock_quarterly_roe(symbol: str)
**Returns**: Return on Equity (quarterly)
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "net_income_common_stockholders": 2321000000,
            "beginning_stockholders_equity": 54000000000,
            "ending_stockholders_equity": 55566666000,
            "avg_equity": 54783333000,
            "roe": 0.0424  # 4.24%
        }
    ]
}
```

### get_stock_quarterly_roa(symbol: str)
**Returns**: Return on Assets (quarterly)
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "net_income_common_stockholders": 2321000000,
            "beginning_total_assets": 120000000000,
            "ending_total_assets": 123456789000,
            "avg_assets": 121728394500,
            "roa": 0.0191  # 1.91%
        }
    ]
}
```

### get_stock_quarterly_roic(symbol: str)
**WARNING**: Not applicable to banks/financial institutions

**Returns**: Return on Invested Capital
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "ebit": 3592000000,
            "tax_rate_for_calcs": 0.15,
            "nopat": 3053200000,  # EBIT × (1 - tax_rate)
            "beginning_invested_capital": 60000000000,
            "ending_invested_capital": 62000000000,
            "avg_invested_capital": 61000000000,
            "roic": 0.0501  # 5.01%
        }
    ]
}
```

### get_stock_quarterly_equity_multiplier(symbol: str)
**WARNING**: Not applicable to banks

**Returns**: Leverage ratio (DuPont component)
```python
{
    "symbol": "TSLA",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "roe": 0.0424,
            "roa": 0.0191,
            "equity_multiplier": 2.22  # ROE / ROA
        }
    ]
}
```

### get_stock_quarterly_asset_turnover(symbol: str)
**Returns**: Asset efficiency (DuPont component)
```python
{
    "symbol": "TSLA",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "roa": 0.0191,
            "net_margin": 0.0922,
            "asset_turnover": 0.207  # ROA / Net Margin
        }
    ]
}
```

## Valuation Ratios

### get_stock_ttm_pe(symbol: str, start_date: str = None, end_date: str = None)
**Parameters**:
- **MAX 1000 rows** (most recent if truncated)

**Returns**: Historical P/E ratio
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "eps_report_date": "2024-12-31",
            "close_price": 234.56,
            "ttm_diluted_eps": 3.64,
            "ttm_pe": 64.43
        }
    ]
}
```

### get_stock_ps_ratio(symbol: str, start_date: str = None, end_date: str = None)
**Returns**: Historical P/S ratio (MAX 1000 rows)
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "fiscal_quarter": "2024-12-31",
            "market_capitalization": 750592000000,
            "ttm_revenue_usd": 95000000000,
            "ps_ratio": 7.90
        }
    ]
}
```

### get_stock_pb_ratio(symbol: str, start_date: str = None, end_date: str = None)
**Returns**: Historical P/B ratio (MAX 1000 rows)
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "fiscal_quarter": "2024-12-31",
            "market_capitalization": 750592000000,
            "book_value_of_equity_usd": 55566666000,
            "pb_ratio": 13.51
        }
    ]
}
```

### get_stock_peg_ratio(symbol: str, start_date: str = None, end_date: str = None)
**Returns**: PEG by earnings & revenue growth (MAX 1000 rows)
```python
{
    "symbol": "TSLA",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "fiscal_quarter": "2024-12-31",
            "ttm_pe": 64.43,
            "eps_yoy_growth": 0.15,  # 15% EPS growth
            "peg_ratio_by_eps": 4.30,  # P/E / EPS growth
            "revenue_yoy_growth": 0.12,
            "peg_ratio_by_revenue": 5.37
        }
    ]
}
```

### get_stock_wacc(symbol: str, start_date: str = None, end_date: str = None)
**Returns**: Weighted Average Cost of Capital (MAX 1000 rows)
```python
{
    "symbol": "TSLA",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "market_capitalization": 750592000000,
            "total_debt": 12000000000,
            "interest_expense": 180000000,
            "tax_rate_for_calcs": 0.15,
            "expected_market_return": 0.1107,  # 10-year S&P 500 CAGR
            "risk_free_rate": 0.0433,  # 10-year Treasury
            "beta_5y": 2.10,
            "weight_of_debt": 0.0157,
            "weight_of_equity": 0.9843,
            "cost_of_debt": 0.0150,
            "cost_of_equity": 0.1848,  # CAPM
            "wacc": 0.1820  # 18.20%
        }
    ]
}
```

## Growth Metrics

All growth APIs return YoY growth rate. Using revenue as example:

### Quarterly Growth
- `get_stock_quarterly_revenue_yoy_growth(symbol)`
- `get_stock_quarterly_operating_income_yoy_growth(symbol)`
- `get_stock_quarterly_ebitda_yoy_growth(symbol)`
- `get_stock_quarterly_net_income_yoy_growth(symbol)`
- `get_stock_quarterly_fcf_yoy_growth(symbol)`
- `get_stock_quarterly_diluted_eps_yoy_growth(symbol)`
- `get_stock_quarterly_ttm_diluted_eps_yoy_growth(symbol)`

### Annual Growth
- `get_stock_annual_revenue_yoy_growth(symbol)`
- `get_stock_annual_operating_income_yoy_growth(symbol)`
- `get_stock_annual_ebitda_yoy_growth(symbol)`
- `get_stock_annual_net_income_yoy_growth(symbol)`
- `get_stock_annual_fcf_yoy_growth(symbol)`

**Returns**:
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "revenue": 25167000000,
            "prev_year_revenue": 22103000000,
            "yoy_growth": 0.1386  # 13.86% growth
        }
    ]
}
```

## Industry Benchmarking

Industry APIs follow same structure as company-level APIs, but aggregate across all companies in the industry.

### Industry Margins
- `get_industry_quarterly_gross_margin(symbol)` - Use symbol to identify industry
- `get_industry_quarterly_net_margin(symbol)`
- `get_industry_quarterly_ebitda_margin(symbol)`

**Returns**:
```python
{
    "industry": "Auto Manufacturers",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "total_gross_profit": 50000000000,  # sum across industry
            "total_revenue": 200000000000,
            "industry_gross_margin": 0.25  # 25%
        }
    ]
}
```

### Industry Valuation
- `get_industry_ttm_pe(symbol, start_date, end_date)` - MAX 1000 rows
- `get_industry_ps_ratio(symbol, start_date, end_date)` - MAX 1000 rows
- `get_industry_pb_ratio(symbol, start_date, end_date)` - MAX 1000 rows

**Returns**:
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "date_range": "2020-01-01 to 2025-01-24",
    "rows_returned": 1000,
    "truncated": true,
    "data": [
        {
            "report_date": "2025-01-24",
            "industry": "Auto Manufacturers",
            "total_market_cap": 1500000000000,
            "total_ttm_net_income": 50000000000,
            "industry_ttm_pe": 30.00
        }
    ]
}
```

### Industry Profitability
- `get_industry_quarterly_roe(symbol)`
- `get_industry_quarterly_roa(symbol)`
- `get_industry_quarterly_equity_multiplier(symbol)`
- `get_industry_quarterly_asset_turnover(symbol)`

**Returns**:
```python
{
    "symbol": "TSLA",
    "currency": "USD",
    "period_type": "quarterly",
    "periods": [...],
    "rows_returned": 20,
    "data": [
        {
            "period": "2024-12-31",
            "industry": "Auto Manufacturers",
            "total_net_income_common_stockholders": 5000000000,
            "total_avg_equity": 100000000000,
            "industry_roe": 0.05  # 5%
        }
    ]
}
```

## Common Response Patterns

### Handling Null Values
All numeric fields may be `null` when data is unavailable:
```python
{
    "revenue": null,  # Not reported for this period
    "net_margin": null  # Cannot calculate (division by zero)
}
```

### Truncation Warnings
When data exceeds limits:
```python
{
    "rows_returned": 1000,
    "truncated": true  # More data exists, use narrower date range
}
```

### Currency Information
All financial data includes currency:
```python
{
    "currency": "USD",  # All amounts in US Dollars
    "statement": [...]
}
```

### Date Formats
All dates use ISO 8601 (YYYY-MM-DD):
```python
{
    "report_date": "2024-12-31",
    "period": "2024-12-31"
}
```