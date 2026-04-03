# Suggested Data Source: FinancialReports.eu API

## Overview

[FinancialReports.eu](https://financialreports.eu) provides a comprehensive, structured API for accessing regulatory filings and company disclosures from **35 official sources** across **30+ countries**. It would complement Defeat Beta's existing market data (prices, financial statements, valuations) by adding a rich layer of **regulatory filing data** — annual reports, interim reports, ESG disclosures, M&A announcements, and more.

## Why This Fits

Defeat Beta currently sources financial statements and SEC filings from the HuggingFace dataset. FinancialReports.eu would extend coverage to:

- **14M+ regulatory filings** from official regulators worldwide
- **33,000+ companies** with ISIN, LEI, and GICS industry classification
- **Global coverage** beyond SEC/EDGAR — including EU (Euronext, FCA UK, BaFin Germany, CNMV Spain, AMF France, etc.), Japan (EDINET), South Korea (OPENDART), Israel (TASE), Switzerland (SIX), Turkey (KAP), and more
- **11 standardized filing categories**: Annual General Meeting, Financial Reporting, Debt Information, Equity Information, ESG Information, M&A/Partnerships/Legal, Investor Communication, Management & Remuneration, Listing/Delisting, Investment Vehicle Info
- **Filing document access**: Direct PDF/document URLs and a Markdown conversion endpoint for LLM-ready text extraction

## API Details

**Base URL**: `https://api.financialreports.eu`
**API Documentation**: [docs.financialreports.eu](https://docs.financialreports.eu/)
**Authentication**: API key via `X-API-Key` header
**Python SDK**: `pip install financial-reports-generated-client` ([GitHub](https://github.com/financial-reports/financial-reports-python))
**Rate Limiting**: Two-tier system (burst limit + monthly quota) with rate limit headers in responses

### Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /companies/` | Search/list 33K+ companies by ticker, ISIN, LEI, country, industry |
| `GET /filings/` | Search 14M+ filings by company, date range, category, type, country, language |
| `GET /filings/{id}/markdown/` | Get filing content as Markdown (ideal for LLM analysis) |
| `GET /companies/{id}/next-annual-report/` | Predicted next annual report date |
| `GET /sources/` | List all 35 regulatory data sources |
| `GET /filing-categories/` | 11 standardized disclosure categories |
| `GET /filing-types/` | Granular filing type taxonomy |
| `GET /countries/` | Country reference data |

### Integration Ideas

1. **Extend `Ticker` class** with a `filings()` method to fetch regulatory filings by ticker/ISIN
2. **LLM-powered filing analysis** — use the `/filings/{id}/markdown/` endpoint to feed annual report text into the existing LLM pipeline (similar to earnings transcript analysis)
3. **Global SEC filings** — extend the current `sec_filing()` method to support non-US regulatory filings
4. **ESG data** — surface ESG-categorized filings alongside financial data
5. **Event detection** — M&A announcements, management changes, listing/delisting events

### Example: Fetching Apple's European Filings

```python
# Using the official Python SDK
from financial_reports_client import Client

client = Client(base_url="https://api.financialreports.eu")
client = client.with_headers({"X-API-Key": "your-api-key"})

# Search for Apple
from financial_reports_client.api.companies import companies_list
companies = companies_list.sync(client=client, search="Apple", page_size=5)

# Or using requests directly
import requests

headers = {"X-API-Key": "your-api-key"}

# Search for Apple
resp = requests.get("https://api.financialreports.eu/companies/",
    headers=headers,
    params={"search": "Apple", "page_size": 5}
)

# Get filings for a company
resp = requests.get("https://api.financialreports.eu/filings/",
    headers=headers,
    params={
        "company_isin": "US0378331005",  # Apple's ISIN
        "categories": "2",               # Financial Reporting
        "page_size": 10
    }
)

# Get filing content as Markdown (for LLM analysis)
resp = requests.get("https://api.financialreports.eu/filings/12345/markdown/",
    headers=headers
)
```

### MCP Server

FinancialReports.eu also offers an [MCP server integration](https://financialreports.eu), making it compatible with Claude.ai and other AI platforms — similar to Defeat Beta's own MCP implementation.

## Data Source Details

| Property | Value |
|---|---|
| Companies covered | 33,230+ |
| Total filings | 14,135,359+ |
| Regulatory sources | 35 (SEC, FCA, EDINET, Euronext, etc.) |
| Filing categories | 11 standardized |
| Country coverage | 30+ countries |
| API format | REST JSON |
| Authentication | API key (`X-API-Key` header) |
| Rate limiting | Burst limit + monthly quota |
| Python SDK | `pip install financial-reports-generated-client` |
| API Documentation | [docs.financialreports.eu](https://docs.financialreports.eu/) |

## Complementary Value

| Defeat Beta (current) | + FinancialReports.eu |
|---|---|
| Stock prices (OHLCV) | Regulatory filing documents |
| Financial statements | Annual/interim report PDFs + Markdown |
| SEC filings (US only) | 35 regulators across 30+ countries |
| Earnings transcripts | ESG disclosures, M&A announcements |
| Valuation metrics | Filing event timeline |
| LLM analysis of transcripts | LLM analysis of full annual reports |
