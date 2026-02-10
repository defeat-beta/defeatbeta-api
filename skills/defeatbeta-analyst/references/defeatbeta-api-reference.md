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

## DCF Valuation

### get_stock_dcf_analysis(symbol: str)
**Purpose**: Generate comprehensive Discounted Cash Flow (DCF) valuation analysis with Excel model

**Parameters**:
- `symbol`: Stock ticker (e.g., "QCOM", "AAPL")

**Returns**: Complete DCF analysis with 5 main components

```python
{
    "symbol": "QCOM",
    "file_path": "/tmp/defeatbeta_tmp/QCOM.xlsx",  # Excel model for detailed review
    
    # 1. Discount Rate (WACC) Estimates
    "discount_rate_estimates": {
        "report_date": "2026-02-06",
        "market_cap": 146541780000.0,
        "beta_5y": 1.21,
        "total_debt": 14817000000.0,
        "interest_expense": 169000000.0,
        "pretax_income": 3547000000.0,
        "tax_provision": 543000000.0,
        "risk_free_rate": 0.0422,  # 10-year Treasury
        "expected_market_return": 0.1287,  # 10-year S&P 500 CAGR
        "weight_of_debt": 0.0918,
        "weight_of_equity": 0.9082,
        "cost_of_debt": 0.0114,  # after-tax
        "cost_of_equity": 0.1469,  # CAPM
        "tax_rate": 0.15,
        "wacc": 0.1343  # 13.43%
    },
    
    # 2. Historical Growth Analysis (3-Year CAGR)
    "growth_estimates": {
        "revenue": {
            "historical": [
                {
                    "date": "2023-09-30",
                    "value": 35820000000.0,
                    "yoy_growth": -0.1896
                },
                {
                    "date": "2024-09-30",
                    "value": 38962000000.0,
                    "yoy_growth": 0.0877
                },
                {
                    "date": "2025-09-30",
                    "value": 44284000000.0,
                    "yoy_growth": 0.1366
                }
            ],
            "cagr_3y": 0.1119  # 11.19%
        },
        "fcf": {
            "historical": [...],
            "cagr_3y": 0.1409  # 14.09%
        },
        "ebitda": {
            "historical": [...],
            "cagr_3y": 0.2252  # 22.52%
        },
        "net_income": {
            "historical": [...],
            "cagr_3y": -0.1247  # -12.47%
        }
    },
    
    # 3. DCF Template (Growth Assumptions & Projections)
    "dcf_template": {
        # Growth Rate Framework
        "decay_factor": 0.9,
        "future_growth_rate_1_5y": 0.1196,  # 11.96%
        "future_growth_rate_1_5y_explanation": {
            "formula": "Revenue_CAGR × 0.4 + FCF_CAGR × 0.3 + EBITDA_CAGR × 0.2 + NI_CAGR × 0.1",
            "description": "Weighted average of historical 3-year CAGRs",
            "components": {
                "revenue_cagr": {"value": 0.1119, "weight": 0.4, "rationale": "Primary growth driver"},
                "fcf_cagr": {"value": 0.1409, "weight": 0.3, "rationale": "Cash generation sustainability"},
                "ebitda_cagr": {"value": 0.2252, "weight": 0.2, "rationale": "Operational efficiency"},
                "net_income_cagr": {"value": -0.1247, "weight": 0.1, "rationale": "Profitability trend"}
            }
        },
        "future_growth_rate_6_10y": 0.0706,  # 7.06% (decayed)
        "future_growth_rate_6_10y_explanation": {
            "formula": "MAX(Growth_1_5Y × Decay_Factor ^ 5, Risk_Free_Rate)",
            "description": "Decayed growth rate with risk-free rate floor",
            "components": {
                "base_growth": 0.1196,
                "decay_factor": 0.9,
                "years_decayed": 5,
                "decayed_growth": 0.0706,
                "risk_free_rate_floor": 0.0422
            },
            "rationale": "Growth naturally slows over time. Floor at risk-free rate ensures minimum growth matches economic baseline"
        },
        "future_growth_rate_terminal": 0.0422,  # 4.22% (10Y Treasury)
        "future_growth_rate_terminal_explanation": {
            "formula": "Risk_Free_Rate (10Y Treasury)",
            "description": "Perpetual growth rate set to risk-free rate",
            "components": {"risk_free_rate": 0.0422},
            "rationale": "Conservative assumption: mature companies cannot grow faster than the economy indefinitely"
        },
        
        # Current Baseline
        "discount_rate": 0.1343,
        "ttm_revenue": 44867000000.0,
        "ttm_revenue_label": "TTM Revenue (USD | 2025-03-31 ~ 2025-12-31)",
        "future_revenue_growth_1_5y": 0.1119,
        "future_revenue_growth_6_10y": 0.0661,
        
        # 10-Year Projections
        "projections": {
            "years": [
                "2025-12-31 (TTM)", "2026/12/31", "2027/12/31", "2028/12/31",
                "2029/12/31", "2030/12/31", "2031/12/31", "2032/12/31",
                "2033/12/31", "2034/12/31", "2035/12/31"
            ],
            "fcf": [
                12926000000.0,  # TTM
                14471790832.52,  # Year 1
                16202439261.97,  # Year 2
                18140051986.37,  # Year 3
                20309379393.31,  # Year 4
                22738131712.69,  # Year 5
                24343792867.60,  # Year 6
                26062838348.76,  # Year 7
                27903274830.18,  # Year 8
                29873674379.97,  # Year 9
                31983214385.83   # Year 10
            ],
            "terminal_value": 385351514831.33,  # Year 10 terminal value
            "total_value": [  # FCF + Terminal Value in Year 10
                12926000000.0, 14471790832.52, ..., 417334729217.16
            ],
            "fcf_margin": [
                0.2881,  # TTM: 28.81%
                0.2901,  # Year 1: 29.01%
                0.2921,  # Year 2: 29.21%
                0.2941,  # Year 3: 29.41%
                0.2962,  # Year 4: 29.62%
                0.2982,  # Year 5: 29.82%
                0.2995,  # Year 6: 29.95%
                0.3008,  # Year 7: 30.08%
                0.3020,  # Year 8: 30.20%
                0.3033,  # Year 9: 30.33%
                0.3046   # Year 10: 30.46%
            ]
        },
        
        # Historical FCF Margin (for validation)
        "historical_fcf_margin": {
            "2021/09/30": 0.2576,  # 25.76%
            "2022/09/30": 0.1546,  # 15.46%
            "2023/09/30": 0.2750,  # 27.50%
            "2024/09/30": 0.2865,  # 28.65%
            "2025/09/30": 0.2895   # 28.95%
        }
    },
    
    # 4. DCF Valuation Output
    "dcf_value": {
        "report_date": "2026-02-06",
        "enterprise_value": 222573239465.57,  # PV of all FCF
        "cash_and_st_investments": 11822000000.0,
        "total_debt": 14817000000.0,
        "equity_value": 219578239465.57,  # EV + Cash - Debt
        "outstanding_shares": 1067000000.0,
        "fair_price": 205.79,  # Equity Value / Shares
        "current_price": 137.34,
        "margin_of_safety": 0.3326  # 33.26%
    },
    
    # 5. Investment Recommendation
    "buy_sell": {
        "fair_price": 205.79,
        "current_price": 137.34,
        "recommendation": "Buy",  # Buy | Hold | Sell
        "upside_potential": 0.4984  # 49.84%
    }
}
```

**Key Features**:
1. **Automated Growth Estimation**: Weighted average of Revenue, FCF, EBITDA, Net Income CAGRs
2. **Three-Stage Growth Model**: Near-term (1-5Y), Mid-term (6-10Y), Terminal (perpetual)
3. **Decay Factor**: Applies 0.9 annual decay to moderate mid-term growth
4. **Risk-Free Floor**: Terminal growth rate floors at 10Y Treasury yield
5. **FCF Margin Tracking**: Projects and validates FCF as % of Revenue
6. **Excel Model Output**: Full model saved to file_path for custom analysis

**Important Validation Checks**:
- **Beta Reasonableness**: Beta < 0.5 for high-risk stocks (e.g., Chinese ADRs) likely underestimates risk
- **Growth Alignment**: Compare growth assumptions against business fundamentals, not just historical averages
- **FCF Margin Trend**: Ensure projected margins align with 5-year historical trend
- **Terminal Rate < WACC**: If Terminal Rate ≥ WACC, model is mathematically invalid

**Usage Example**:
```python
# Get DCF analysis
result = get_stock_dcf_analysis("QCOM")

# Access components
wacc = result["discount_rate_estimates"]["wacc"]  # 0.1343
fair_price = result["dcf_value"]["fair_price"]  # $205.79
current_price = result["dcf_value"]["current_price"]  # $137.34
recommendation = result["buy_sell"]["recommendation"]  # "Buy"
upside = result["buy_sell"]["upside_potential"]  # 0.4984 (49.84%)

# Review detailed model
excel_path = result["file_path"]  # "/tmp/defeatbeta_tmp/QCOM.xlsx"
```

**Special Considerations for Chinese ADRs** (BABA, PDD, JD, etc.):
- Beta calculations often show 0.3-0.4, but real risk is higher (1.0-1.5 more appropriate)
- Systematic risks not captured: VIE structure, regulatory, geopolitical
- Growth assumptions may be overly conservative if based solely on historical data
- **Recommended approach**: Use tool output as baseline, then manually adjust assumptions

**Cross-Validation Recommended**:
After generating DCF fair value, compare with:
- `get_stock_ttm_pe()` - Is P/E ratio reasonable vs industry?
- `get_stock_ps_ratio()` - Is P/S ratio at historical extremes?
- `get_stock_quarterly_revenue_yoy_growth()` - Does growth justify valuation?
- `get_industry_ttm_pe()` - How does fair value compare to industry average?

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