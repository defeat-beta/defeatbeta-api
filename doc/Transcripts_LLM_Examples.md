# Example: Using LLM for Earnings Call Transcript Analysis
> [!NOTE]
> Imagine reading a lengthy earnings call transcript to extract key data mentioned by the CEO, CFO, or analysts, which could take at least 10 minutes. Using an LLM, this can be done in just a few seconds.
> 
> This document provides an example of how to use the large language model to summarize key financial data from earnings call transcripts.

## Prerequisites
To run this example, you need: An OpenAI-compatible API key (`OPEN_AI_API_KEY`). 

Our tests show that even free, small-parameter models can deliver excellent results.

> [!TIP]
> You can obtain a free API for small-parameter models from [SiliconFlow's Chinese website](https://www.siliconflow.cn/pricing).
> 
> For higher accuracy and performance, consider using larger models from [OpenAI](https://openai.com/index/openai-api/), [DeepSeek](https://api-docs.deepseek.com/), [QWen](https://qwen.ai/apiplatform), or [Gemini](https://ai.google.dev/gemini-api/docs).

## Example Code
Below is an example demonstrating how to fetch key financial metrics from earnings call transcripts using LLM model.

```python
import logging
from openai import OpenAI
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.client.openai_conf import OpenAIConfiguration

# Initialize the Ticker with debug logging
ticker = Ticker("AMD", log_level=logging.DEBUG)

# Fetch earnings call transcripts
transcripts = ticker.earning_call_transcripts()

# Configure the OpenAI client
llm = OpenAI(
    api_key="OPEN_AI_API_KEY",  # Replace with your OPEN_AI_API_KEY
    base_url="https://api.siliconflow.cn/v1"
)

# Summarize key financial data for Q2 2025 with llm
res = transcripts.summarize_key_financial_data_with_ai(2025, 2, llm, OpenAIConfiguration())
print(res.to_string())
```

---

```text
   symbol  fiscal_year  fiscal_quarter     speaker paragraph_number                                  key_financial_metric         value currency_code
0     AMD         2025               2  Lisa T. Su                3                        total_revenue_for_this_quarter  7.700000e+09           USD
1     AMD         2025               2  Jean X. Hu                4                    gaap_gross_margin_for_this_quarter  4.300000e-01           USD
2     AMD         2025               2  Lisa T. Su                3                non_gaap_gross_margin_for_this_quarter  5.400000e-01           USD
3     AMD         2025               2  Jean X. Hu                4               gaap_operating_expense_for_this_quarter  2.400000e+09           USD
4     AMD         2025               2        None             None           non_gaap_operating_expense_for_this_quarter           NaN          None
5     AMD         2025               2  Jean X. Hu                4                gaap_operating_income_for_this_quarter  8.970000e+08           USD
6     AMD         2025               2        None             None            non_gaap_operating_income_for_this_quarter           NaN          None
7     AMD         2025               2  Jean X. Hu                4         gaap_operating_income_margin_for_this_quarter  1.200000e-01           USD
8     AMD         2025               2        None             None     non_gaap_operating_income_margin_for_this_quarter           NaN          None
9     AMD         2025               2        None             None                      gaap_net_income_for_this_quarter           NaN          None
10    AMD         2025               2        None             None                  non_gaap_net_income_for_this_quarter           NaN          None
11    AMD         2025               2        None             None                               ebitda_for_this_quarter           NaN          None
12    AMD         2025               2        None             None                      adjusted_ebitda_for_this_quarter           NaN          None
13    AMD         2025               2  Jean X. Hu                4       gaap_diluted_earning_per_share_for_this_quarter  4.800000e-01           USD
14    AMD         2025               2        None             None   non_gaap_diluted_earning_per_share_for_this_quarter           NaN          None
15    AMD         2025               2  Lisa T. Su                3                                  fcf_for_this_quarter  1.200000e+09           USD
16    AMD         2025               2  Jean X. Hu                4                  total_cash_position_for_this_quarter  5.900000e+09           USD
17    AMD         2025               2  Jean X. Hu                4                     share_repurchase_for_this_quarter  4.780000e+08           USD
18    AMD         2025               2        None             None                                capex_for_this_quarter           NaN          None
19    AMD         2025               2  Jean X. Hu                4               total_revenue_forecast_for_next_quarter  8.700000e+09           USD
20    AMD         2025               2        None             None           gaap_gross_margin_forecast_for_next_quarter           NaN          None
21    AMD         2025               2  Jean X. Hu                4       non_gaap_gross_margin_forecast_for_next_quarter  5.400000e-01           USD
22    AMD         2025               2        None             None      gaap_operating_expense_forecast_for_next_quarter           NaN          None
23    AMD         2025               2  Jean X. Hu                4  non_gaap_operating_expense_forecast_for_next_quarter  2.550000e+09           USD
24    AMD         2025               2        None             None      gaap_earning_per_share_forecast_for_next_quarter           NaN          None
25    AMD         2025               2        None             None  non_gaap_earning_per_share_forecast_for_next_quarter           NaN          None
26    AMD         2025               2        None             None                       capex_forecast_for_next_quarter           NaN          None
```

> [!IMPORTANT]
> For key financial metrics labeled as `xxx_forecast_for_next_quarter`, the original text often provides a forecast range for the next quarter. In such cases, the model will output the midpoint of that range. Note that this value may not be explicitly stated in the transcripts.
> 
> In contrast, metrics labeled as `xxx_for_this_quarter` will be extracted directly from the transcripts without any calculation.
> 
> If a metric is not mentioned in the transcripts, return null for that field.

## Supported LLM Models
This feature leverages the function-calling capabilities of large language models, so it requires a model with this functionality to work successfully. Fortunately, most large language models support this feature.

Currently supported models include:

| Series       | Models                                                                                                                                                                                       |
|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **DeepSeek** | DeepSeek-V3, DeepSeek-V3.1, DeepSeek-R1-0528, DeepSeek-R1 (partial environments)                                                                                                             |
| **Qwen**     | Qwen-2.5 (e.g., Qwen-2.5-7B), Qwen-Plus, Qwen-Max, Qwen-Flash, Qwen-Turbo, Qwen3                                                                                                             |
| **OpenAI**   | GPT-4 series (e.g., gpt-4, gpt-4o), o3, o3-mini, o4-mini, gpt-oss-20B, gpt-oss-120B                                                                                                          |
| **Gemini**   | Gemini 2.5 Flash-Lite, Gemini 2.5 Flash + Live API, Gemini 2.0 Flash + Live API, Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.0 Flash, Gemini 2.0 Flash-Lite, Gemini 1.5 Pro, Gemini 1.5 Flash |

## Configuration
Below is an example of how to set up the OpenAIConfiguration class for fine-tuned control.
```python
class OpenAIConfiguration:
    def __init__(
        self,
        model="Qwen/Qwen3-8B",
        temperature=0.01,
        top_p=0.95,
        stream=False
    ):
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.stream = stream
```

- model: Specifies the language model to use (e.g., Qwen/Qwen3-8B). See Supported Models for more details.
- temperature: Controls the randomness of the output (default: 0.01 for deterministic responses).
- top_p: Controls the diversity via nucleus sampling (default: 0.95).
- stream: Enables streaming responses if set to True (default: False).