# Define the two core schemas
AMOUNT_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "value_vocabulary": {
            "type": "number",
            "description": "Numerical value extracted from the transcript, without scaling or conversion. For example: if transcript says 'a billion', return 'a' with unit 'billion'. For forecasts, if a range is provided (min/max), return the midpoint as the value."
        },
        "unit": {
            "type": "string",
            "description": "Unit of magnitude exactly as reported in the transcript (e.g., trillion, million, billion, thousand) or 'per_share' for EPS metrics."
        },
        "currency_code": {
            "type": "string",
            "description": "ISO 4217 currency code, e.g., USD, CNY, EUR"
        },
        "speaker": {
            "type": "string",
            "description": "Name or role of the speaker who provided this number in the transcript, e.g., 'CFO', 'CEO', or 'John Smith'."
        },
        "paragraph_number": {
            "type": "number",
            "description": "The sequential number of the paragraph in the transcript where this information was mentioned. Useful for traceability."
        }
    }
}

PERCENT_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "value_vocabulary": {
            "type": "number",
            "description": "Numerical percentage value extracted from the transcript, e.g., 72.5 for 72.5%. For forecasts, if a range is provided (min/max), return the midpoint as the value."
        },
        "unit": {
            "type": "string",
            "description": "Always '%' to indicate margin is expressed as a percentage."
        },
        "speaker": {
            "type": "string",
            "description": "Name or role of the speaker who provided this number in the transcript, e.g., 'CFO', 'CEO', or 'John Smith'."
        },
        "paragraph_number": {
            "type": "number",
            "description": "The sequential number of the paragraph in the transcript where this information was mentioned. Useful for traceability."
        }
    }
}

# Define all financial fields
KEY_FINANCIAL_FIELDS = [
    # Current quarter amounts
    {"name": "total_revenue_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Total revenue for the current quarter. Return null if unavailable."},
    {"name": "gaap_operating_expense_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP operating expenses (OpEx) for the current quarter, as reported in the transcript. Represents total costs and expenses incurred in operations under GAAP (e.g., R&D, SG&A). Return null if unavailable."},
    {"name": "non_gaap_operating_expense_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP operating expenses (OpEx) for the current quarter, as reported in the transcript. Return null if unavailable."},
    {"name": "gaap_operating_income_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP operating income as reported in the transcript. Represents profit from operations under GAAP. Return null if unavailable."},
    {"name": "non_gaap_operating_income_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP operating income as reported in the transcript. Represents profit from operations under Non-GAAP. Return null if unavailable."},
    {"name": "gaap_net_income_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP net income for the current quarter. Return null if unavailable."},
    {"name": "non_gaap_net_income_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP net income for the current quarter. Return null if unavailable."},
    {"name": "ebitda_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "EBITDA for the current quarter. Return null if unavailable."},
    {"name": "adjusted_ebitda_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Adjusted EBITDA for the current quarter. Return null if unavailable."},
    {"name": "fcf_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Free cash flow (FCF) or equivalent cash flow metrics disclosed for the current quarter, such as free cash flow, operating cash flow, net cash provided by operating activities, or cash generated. Return null if not mentioned in the transcript."},
    {"name": "total_cash_position_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Total cash position, including cash, cash equivalents, marketable securities, and short-term investments, as reported in the transcript. May appear under different names (e.g., 'cash and equivalents', 'short-term investments', 'cash & marketable securities'). Return null if unavailable."},
    {"name": "share_repurchase_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Total amount of share repurchases conducted during the current quarter, as reported in the transcript. May appear under different names (e.g., 'share buybacks', 'repurchase program', 'stock repurchase', 'share repurchase'). Return null if unavailable."},
    {"name": "capex_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Capital expenditures (CapEx) for the current quarter, as reported in the transcript. May appear under different names (e.g., 'CapEx investment', 'capital spending', 'capital investments', 'purchases of property and equipment'). Return null if unavailable."},

    # Current quarter percentages
    {"name": "gaap_gross_margin_for_this_quarter", "schema": PERCENT_SCHEMA,
     "desc": "GAAP gross margin (gross profit as a percentage of revenue) for the current quarter, as disclosed in the transcript. May appear as 'gross margin', 'GAAP gross margin', or 'gross profit margin'. Return null if unavailable."},
    {"name": "non_gaap_gross_margin_for_this_quarter", "schema": PERCENT_SCHEMA,
     "desc": "Non-GAAP gross margin (gross profit as a percentage of revenue) for the current quarter, as disclosed in the transcript. May appear as 'gross margin', 'non-GAAP gross margin', or 'gross profit margin'. Return null if unavailable."},
    {"name": "gaap_operating_income_margin_for_this_quarter", "schema": PERCENT_SCHEMA,
     "desc": "GAAP operating income margin for the current quarter, as reported in the transcript. Represents operating income as a percentage of total revenue under GAAP. Return null if unavailable."},
    {"name": "non_gaap_operating_income_margin_for_this_quarter", "schema": PERCENT_SCHEMA,
     "desc": "Non-GAAP operating income margin for the current quarter, as reported in the transcript. Represents operating income as a percentage of total revenue under Non-GAAP. Return null if unavailable."},

    # Current quarter EPS
    {"name": "gaap_diluted_earnings_per_share_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP Diluted Earnings per Share (EPS) for the current quarter, as disclosed in the transcript. This may appear as 'diluted earnings per share' or 'diluted earnings per ADS'. Return null if unavailable."},
    {"name": "non_gaap_diluted_earnings_per_share_for_this_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP Diluted Earnings per Share (EPS) for the current quarter, as disclosed in the transcript. This may appear as 'non-GAAP diluted earnings per share' or 'non-GAAP diluted earnings per ADS'. Return null if unavailable."},

    # Next quarter forecasts
    {"name": "total_revenue_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Total revenue forecast for the next quarter as a single numerical value. Return null if unavailable."},
    {"name": "gaap_gross_margin_forecast_for_next_quarter", "schema": PERCENT_SCHEMA,
     "desc": "GAAP gross margin forecast for the next quarter, expressed as gross profit as a percentage of revenue. In transcripts, this may be referred to as 'gross margin', 'GAAP gross margin', or 'gross profit margin'. Return null if unavailable."},
    {"name": "non_gaap_gross_margin_forecast_for_next_quarter", "schema": PERCENT_SCHEMA,
     "desc": "Non-GAAP gross margin forecast for the next quarter, expressed as gross profit as a percentage of revenue. In transcripts, this may be referred to as 'gross margin', 'non-GAAP gross margin', or 'gross profit margin'. Return null if unavailable."},
    {"name": "gaap_operating_income_margin_forecast_for_next_quarter", "schema": PERCENT_SCHEMA,
     "desc": "Forecasted GAAP operating income margin for the next quarter, as reported in the transcript. Return null if unavailable."},
    {"name": "non_gaap_operating_income_margin_forecast_for_next_quarter", "schema": PERCENT_SCHEMA,
     "desc": "Forecasted Non-GAAP operating income margin for the next quarter, as reported in the transcript. Return null if unavailable."},
    {"name": "gaap_operating_expense_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Forecasted GAAP operating expenses (OpEx) for the next quarter, as reported in the transcript. Return null if unavailable."},
    {"name": "non_gaap_operating_expense_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Forecasted Non-GAAP operating expenses (OpEx) for the next quarter, as reported in the transcript. Return null if unavailable."},
    {"name": "ebitda_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Forecasted EBITDA for the next quarter. Return null if unavailable."},
    {"name": "adjusted_ebitda_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Forecasted Adjusted EBITDA for the next quarter. Return null if unavailable."},
    {"name": "gaap_earnings_per_share_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP Earnings per Share forecast for the next quarter. This may appear as 'earnings per share' or 'earnings per ADS'. Return null if unavailable."},
    {"name": "non_gaap_earnings_per_share_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP Earnings per Share forecast for the next quarter. In transcripts, this may appear as 'non-GAAP EPS', 'non-GAAP earnings per share', or 'non-GAAP earnings per ADS'. Return null if unavailable."},
    {"name": "capex_forecast_for_next_quarter", "schema": AMOUNT_SCHEMA,
     "desc": "Forecasted capital expenditures (CapEx) for the next quarter, as reported in the transcript. May appear under different terms (e.g., 'CapEx investment', 'capital spending', 'capital investments', 'purchases of property and equipment'). Return null if unavailable."},

    # Full fiscal year forecasts
    {"name": "total_revenue_forecast_for_full_fiscal_year", "schema": AMOUNT_SCHEMA,
     "desc": "Total revenue forecast for the full fiscal year (FY) as a single numerical value. Return null if unavailable."},
    {"name": "gaap_earnings_per_share_forecast_for_full_fiscal_year", "schema": AMOUNT_SCHEMA,
     "desc": "GAAP Earnings per Share forecast for the full fiscal year (FY). Return null if unavailable."},
    {"name": "non_gaap_earnings_per_share_forecast_for_full_fiscal_year", "schema": AMOUNT_SCHEMA,
     "desc": "Non-GAAP Earnings per Share forecast for the full fiscal year (FY). Return null if unavailable."}
]

# Build key_financial_data properties
key_financial_properties = {}
for field in KEY_FINANCIAL_FIELDS:
    schema = field["schema"].copy()
    schema["description"] = field["desc"]
    key_financial_properties[field["name"]] = schema

# Required fields
required_key_fields = [field["name"] for field in KEY_FINANCIAL_FIELDS]

# Full schema
FUNCTION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_key_financial_data",
        "description": "Based on the user's question and all contextual information, reason step by step internally and provide structured output strictly following this schema.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "user_question": {
                    "type": "string",
                    "description": "Repeat the original question exactly as it is."
                },
                "key_financial_data": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Based on the earnings call transcript, extract and organize key financial data. If a field is not mentioned, return null for that field. For any non-null field value you return, you MUST include the 'paragraph_number' where the source data appears in the transcript. If the value is inferred or calculated (e.g., taking a midpoint of a range), you MUST include the 'paragraph_number' where the original reference occurred.",
                    "properties": key_financial_properties,
                    "required": required_key_fields
                }
            },
            "required": ["user_question", "key_financial_data"]
        }
    }
}
