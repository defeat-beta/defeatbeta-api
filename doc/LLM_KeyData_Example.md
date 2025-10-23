<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Example: Using LLMs to Extract Key Financial Data for Earnings Call Transcript Analysis](#example-using-llms-to-extract-key-financial-data-for-earnings-call-transcript-analysis)
  - [Prerequisites](#prerequisites)
  - [Example Code](#example-code)
  - [Supported LLM Models](#supported-llm-models)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Example: Using LLMs to Extract Key Financial Data for Earnings Call Transcript Analysis
> [!NOTE]
> Imagine reading a lengthy earnings call transcript to extract key data mentioned by the CEO, CFO, or analysts, which could take at least 10 minutes. Using an LLM, this can be done in just a few seconds.
> 
> This document provides an example of how to use the large language model to summarize key financial data from earnings call transcripts.

## Prerequisites
To run this example, you need: 
1. An OpenAI-compatible API key (`OPEN_AI_API_KEY`)
2. A LLM model with a function call tools capability.
3. A LLM model with a thinking capability.

Our tests show that even free, small-parameter models(e.g. [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B)) can deliver excellent results.

> [!TIP]
> You can obtain a free API for small-parameter models from [SiliconFlow's Chinese website](https://www.siliconflow.cn/pricing).
> 
> For higher accuracy and performance, consider using larger models from [OpenAI](https://openai.com/index/openai-api/), [DeepSeek](https://api-docs.deepseek.com/), [QWen](https://qwen.ai/apiplatform), or [Gemini](https://ai.google.dev/gemini-api/docs).

## Example Code
Below is an example demonstrating how to fetch key financial metrics from earnings call transcripts using LLM model.

```python
from openai import OpenAI
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.client.openai_conf import OpenAIConfiguration

# Initialize the Ticker
ticker = Ticker("AMD")

# Fetch earnings call transcripts
transcripts = ticker.earning_call_transcripts()

# Configure the OpenAI client
llm = OpenAI(
    api_key="OPEN_AI_API_KEY",  # Replace with your OPEN_AI_API_KEY
    base_url="OPEN_AI_API_END_POINT"  # Replace with your OPEN_AI_API_END_POINT
)

# Summarize key financial data for Q2 2025 with llm
res = transcripts.summarize_key_financial_data_with_ai(
  2025, 
  2, 
  llm, 
  OpenAIConfiguration(model='Qwen/Qwen3-8B'))
print(res.to_string())
```

---

```text
   symbol  fiscal_year  fiscal_quarter     speaker paragraph_number                       key_financial_metric        time_scope         value currency_code
0     AMD         2025               2  Lisa T. Su                3                              total_revenue      this_quarter  7.700000e+09           USD
1     AMD         2025               2  Jean X. Hu                4                          gaap_gross_margin      this_quarter  4.300000e-01           USD
2     AMD         2025               2  Lisa T. Su                3                      non_gaap_gross_margin      this_quarter  5.400000e-01           USD
3     AMD         2025               2  Jean X. Hu                4                     gaap_operating_expense      this_quarter  2.400000e+09           USD
4     AMD         2025               2        None             None                 non_gaap_operating_expense      this_quarter           NaN          None
5     AMD         2025               2  Jean X. Hu                4                      gaap_operating_income      this_quarter  8.970000e+08           USD
6     AMD         2025               2        None             None                  non_gaap_operating_income      this_quarter           NaN          None
7     AMD         2025               2  Jean X. Hu                4               gaap_operating_income_margin      this_quarter  1.200000e-01           USD
8     AMD         2025               2        None             None           non_gaap_operating_income_margin      this_quarter           NaN          None
9     AMD         2025               2        None             None                            gaap_net_income      this_quarter           NaN          None
10    AMD         2025               2        None             None                        non_gaap_net_income      this_quarter           NaN          None
11    AMD         2025               2        None             None                                     ebitda      this_quarter           NaN          None
12    AMD         2025               2        None             None                            adjusted_ebitda      this_quarter           NaN          None
13    AMD         2025               2  Jean X. Hu                4            gaap_diluted_earnings_per_share      this_quarter  4.800000e-01           USD
14    AMD         2025               2        None             None        non_gaap_diluted_earnings_per_share      this_quarter           NaN          None
15    AMD         2025               2  Lisa T. Su                3                                        fcf      this_quarter  1.200000e+09           USD
16    AMD         2025               2  Jean X. Hu                4                        total_cash_position      this_quarter  5.900000e+09           USD
17    AMD         2025               2  Jean X. Hu                4                           share_repurchase      this_quarter  4.780000e+08           USD
18    AMD         2025               2        None             None                                      capex      this_quarter           NaN          None
19    AMD         2025               2  Jean X. Hu                4                     total_revenue_forecast      next_quarter  8.700000e+09           USD
20    AMD         2025               2        None             None                 gaap_gross_margin_forecast      next_quarter           NaN          None
21    AMD         2025               2  Jean X. Hu                4             non_gaap_gross_margin_forecast      next_quarter  5.400000e-01           USD
22    AMD         2025               2        None             None      gaap_operating_income_margin_forecast      next_quarter           NaN          None
23    AMD         2025               2        None             None  non_gaap_operating_income_margin_forecast      next_quarter           NaN          None
24    AMD         2025               2        None             None            gaap_operating_expense_forecast      next_quarter           NaN          None
25    AMD         2025               2  Jean X. Hu                4        non_gaap_operating_expense_forecast      next_quarter  2.550000e+09           USD
26    AMD         2025               2        None             None                            ebitda_forecast      next_quarter           NaN          None
27    AMD         2025               2        None             None                   adjusted_ebitda_forecast      next_quarter           NaN          None
28    AMD         2025               2        None             None           gaap_earnings_per_share_forecast      next_quarter           NaN          None
29    AMD         2025               2        None             None       non_gaap_earnings_per_share_forecast      next_quarter           NaN          None
30    AMD         2025               2        None             None                             capex_forecast      next_quarter           NaN          None
31    AMD         2025               2        None             None                     total_revenue_forecast  full_fiscal_year           NaN          None
32    AMD         2025               2        None             None           gaap_earnings_per_share_forecast  full_fiscal_year           NaN          None
33    AMD         2025               2        None             None       non_gaap_earnings_per_share_forecast  full_fiscal_year           NaN          None
```

---

> [!IMPORTANT]
> For key financial metrics labeled as `xxx_forecast`, the original text often provides a forecast range for the next quarter. In such cases, the model will output the midpoint of that range. Note that this value may not be explicitly stated in the transcripts.
> 
> In contrast, metrics not labeled as `xxx_forecast` will be extracted directly from the transcripts without any calculation.
> 
> If a metric is not mentioned in the transcripts, return null for that field.