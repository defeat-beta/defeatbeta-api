<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Main Usage Index](#main-usage-index)
  - [📊 Stock Evaluation Dimensions](#-stock-evaluation-dimensions)
  - [💎 DCF Valuation Analysis](#-dcf-valuation-analysis)
  - [📰 Generate Analysis Report](#-generate-analysis-report)
  - [🤖 LLM-Powered Analysis](#-llm-powered-analysis)
  - [🏦 Economy Analysis](#-economy-analysis)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Main Usage Index


---
## 📊 Stock Evaluation Dimensions

> [!TIP]
> The project evaluates stocks across several key dimensions:
> 
> [Information](api/Info_Examples.md) includes `profile`, `sec filing`, `officers`, `earnings call transcripts`, `financial news` etc.
> 
> [Finance](api/Finance_Examples.md) includes `price`, `statement`, `earning calendar`, `earnings report`, `splits`, `dividends`, `revenue forecast`, `earnings forecast`, `summary`, `revenue breakdown`, `geography breakdown`, `product breakdown` etc.
> 
> [Profitability](api/Profitability_Examples.md) includes `gross margin`, `operating margin`, `net margin`, `ebitda margin`, `fcf margin` etc.
> 
> [Growth](api/Growth_Examples.md) includes `revenue yoy growth`, `operating income yoy growth`, `net income yoy growth`, `fcf yoy growth`, `eps yoy growth` etc.
> 
> [Value](api/Value_Examples.md) includes `ttm-eps`, `ttm-pe`, `historical-market-cap`, `historical-ps-ratio`, `historical-pb-ratio`, `historical-peg-ratio`, `historical-roe`, `historical-roa`, `historical-roic`, `historical-wacc`, `historical-equity-multiplier`, `historical-assert-turnover`, `industry-ttm-pe`, `industry-ps-ratio`, `industry-pb-ratio`, `industry-roe-ratio`, `industry-roa-ratio`, `industry-equity-multiplier`, `industry-net-margin`, `industry-asset-turnover` etc.

---

## 💎 DCF Valuation Analysis

> [!TIP]
> This project provides automated DCF (Discounted Cash Flow) valuation analysis with Excel output.
>
> [DCF Valuation](api/DCF_Examples.md) generates a comprehensive Excel workbook containing `discount rate estimates`, `growth estimates`, `10-year cash flow projections`, `enterprise value`, `equity value`, `fair price`, and `buy/sell recommendations`.

---

## 📰 Generate Analysis Report
> [!TIP]
> This project can also generate an HTML Tearsheets report. See the [linked document](api/Report_Examples.md) for details.

---

## 🤖 LLM-Powered Analysis

> [!TIP]
> This project also offers the capability to analyze data based on Large Language Models (LLMs).
> 1. [Key Financial Data Extraction](api/LLM_KeyData_Example.md) : Analyze earnings call transcripts based on Large Language Models (LLMs) to extract the key financial data mentioned within.
> 2. [Financial Metrics Changes Analysis](api/LLM_ChangeData_Example.md): Analyze earnings call transcripts based on Large Language Models (LLMs) to analyze key quarterly financial changes and their causes.
> 3. [Financial Metrics Forecast Analysis](api/LLM_ForecastData_Example.md): Analyze earnings call transcripts based on Large Language Models (LLMs) to analyze key quarterly financial forecast and their causes.
> 4. [MCP Server](../mcp/README.md): A MCP server implementation for `defeatbeta-api, provides AI access analysis through MCP.

---

## 🏦 Economy Analysis
> [!TIP]
> This project also supports some economic and market data. see [Economy Examples](api/Economy_Examples.md)
> It includes `sp500-historical-annual-returns`, `sp500-cagr-returns`, `daily-par-yield-curve`

---