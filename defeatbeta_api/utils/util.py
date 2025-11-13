import json
import os
import platform
import re
import tempfile
from importlib.resources import files
from typing import List, Dict, Any

import nltk
import numpy as np
import pandas as pd
import psutil
from pandas import DataFrame

from defeatbeta_api.__version__ import __version__
from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.template.transcripts_extract_fin_data_tools import FUNCTION_SCHEMA


def validate_memory_limit(memory_limit: str) -> str:
    valid_units = {"KB", "MB", "GB", "TB", "KiB", "MiB", "GiB", "TiB"}

    pattern = r"^\d+\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)$"
    if re.match(pattern, memory_limit.strip(), re.IGNORECASE):
        return memory_limit.strip()

    # Handle percentage-based memory limit
    if memory_limit.endswith("%"):
        try:
            percentage = float(memory_limit[:-1].strip()) / 100
            if not 0 < percentage <= 1:
                raise ValueError("Percentage must be between 0 and 100")
            # Get system memory
            total_memory = psutil.virtual_memory().total
            target_memory = total_memory * percentage
            # Convert to GB (most common unit for DuckDB)
            target_memory_gb = int(target_memory / (1024 ** 3))  # Convert bytes to GB
            if target_memory_gb < 1:
                raise ValueError("Calculated memory limit is too small (< 1GB)")
            return f"{target_memory_gb}GB"
        except Exception as e:
            raise ValueError(f"Invalid percentage memory limit: {str(e)}")

    raise ValueError(
        f"Invalid memory_limit: '{memory_limit}'. Expected format: e.g., '10GB', '1000MB'. "
        f"Valid units: {', '.join(valid_units)}"
    )

def nltk_sentences(content: str) -> List[str]:
    return nltk.sent_tokenize(content)

def validate_nltk_directory(name: str) -> str:
    if platform.system() in ("Darwin", "Linux"):
        temp_dir = "/tmp"
    else:
        temp_dir = tempfile.gettempdir()
    cache_dir = os.path.join(temp_dir, name)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def validate_httpfs_cache_directory(name: str) -> str:
    if platform.system() in ("Darwin", "Linux"):
        temp_dir = "/tmp"
    else:
        temp_dir = tempfile.gettempdir()
    cache_dir = os.path.join(temp_dir, name, __version__)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def load_item_dictionary() -> Dict[str, str]:
    text = files("defeatbeta_api.data.template").joinpath('dictionary.json').read_text(encoding="utf-8")
    data = json.loads(text)
    return {key: str(value) for key, value in data.items()}

def load_financial_currency() -> Dict[str, str]:
    text = files("defeatbeta_api.data.template").joinpath('financial_currency.json').read_text(encoding="utf-8")
    data = json.loads(text)
    return {key: str(value) for key, value in data.items()}

def income_statement_template_type(df: DataFrame) -> str:
    if not df.query("item_name == 'non_interest_income'").empty:
        return "bank"
    elif not df.query("item_name == 'total_premiums_earned'").empty:
        return "insurance"
    else:
        return "default"

def balance_sheet_template_type(df: DataFrame) -> str:
    if not df.query("item_name == 'cash_cash_equivalents_and_federal_funds_sold'").empty:
        return "bank"
    elif not df.query("item_name == 'current_assets'").empty:
        return "default"
    else:
        return "insurance"

def cash_flow_template_type(df: DataFrame) -> str:
    if not df.query("item_name == 'depreciation_amortization_depletion'").empty:
        return "default"
    else:
        return "insurance"

def load_finance_template(template_name: str, template_type: str) -> Dict[str, FinanceItem]:
    json_data = files("defeatbeta_api.data.template").joinpath(template_name + "_" + template_type + ".json").read_text(encoding="utf-8")
    return parse_finance_item_template(json_data)

def parse_all_title_keys(items: List['FinanceItem'],
                        finance_item_title_keys: Dict[str, str]) -> None:
    for item in items:
        finance_item_title_keys[item.get_title()] = item.get_key()
        if not item.children_is_empty():
            parse_all_title_keys(item.get_children(), finance_item_title_keys)


def parse_all_key_titles(items: List['FinanceItem'],
                         finance_item_key_titles: Dict[str, str]) -> None:
    for item in items:
        finance_item_key_titles[item.get_key()] = item.get_title()
        if not item.children_is_empty():
            parse_all_key_titles(item.get_children(), finance_item_key_titles)

def parse_finance_item_template(json_data: str) -> Dict[str, FinanceItem]:
    data = json.loads(json_data)
    template_array = data["FinancialTemplateStore"]["template"]

    finance_template = {}
    for item in _parse_finance_item_template(template_array):
        finance_template[item.title] = item
    return finance_template


def _parse_finance_item_template(array: List[Dict]) -> List[FinanceItem]:
    result = []
    for item in array:
        children = item.get("children")
        finance_item = FinanceItem(
            key=item["key"],
            title=item["title"],
            children=_parse_finance_item_template(children) if children else [],
            spec=item.get("spec"),
            ref=item.get("ref"),
            industry=item.get("industry")
        )
        result.append(finance_item)
    return result

def load_transcripts_summary_prompt_temp() -> str:
    text = files("defeatbeta_api.data.template").joinpath('transcripts_extract_fin_data_prompt.md').read_text(encoding="utf-8")
    return text

def load_transcripts_analyze_change_prompt() -> str:
    text = files("defeatbeta_api.data.template").joinpath('transcripts_analyze_fin_change_prompt.md').read_text(encoding="utf-8")
    return text

def load_transcripts_analyze_forecast_prompt() -> str:
    text = files("defeatbeta_api.data.template").joinpath('transcripts_analyze_fin_forecast_prompt.md').read_text(encoding="utf-8")
    return text

def load_transcripts_summary_tools_def() -> Dict[str, Any]:
    text = json.dumps([FUNCTION_SCHEMA], indent=2)
    data = json.loads(text)
    return data

def load_transcripts_analyze_change_tools() -> Dict[str, Any]:
    text = files("defeatbeta_api.data.template").joinpath('transcripts_analyze_fin_change_tools.json').read_text(encoding="utf-8")
    data = json.loads(text)
    return data

def load_transcripts_analyze_forecast_tools() -> Dict[str, Any]:
    text = files("defeatbeta_api.data.template").joinpath('transcripts_analyze_fin_forecast_tools.json').read_text(encoding="utf-8")
    data = json.loads(text)
    return data

def load_sp500_historical_annual_returns() -> pd.DataFrame:
    text = files("defeatbeta_api.data.template").joinpath('sp500_historical_annual_returns.json').read_text(encoding="utf-8")
    data = json.loads(text)

    df = pd.DataFrame(list(data.items()), columns=["report_date", "annual_returns"])

    df["report_date"] = pd.to_datetime(df["report_date"])

    df = df.sort_values("report_date").reset_index(drop=True)

    return df

def sp500_cagr_returns(years: int) -> pd.DataFrame:
    annual_returns = load_sp500_historical_annual_returns()
    recent = annual_returns.tail(years).copy()

    end_value = np.prod(1 + recent["annual_returns"].values)

    cagr = end_value ** (1 / years) - 1

    return pd.DataFrame([{"years": years, "cagr_returns": round(cagr, 4)}])

def sp500_cagr_returns_rolling(years: int) -> pd.DataFrame:
    if years <= 0:
        raise ValueError("years must be a positive integer")

    df = load_sp500_historical_annual_returns().copy()
    df = df.sort_values("report_date").reset_index(drop=True)

    n = len(df)
    if n < years:
        return pd.DataFrame(columns=[
            "start_date", "end_date", "start_year", "end_year", f"cagr_returns_{years}_years"
        ])

    returns_series = df["annual_returns"]
    rolling_prod = (1 + returns_series).rolling(window=years, min_periods=years).apply(np.prod, raw=True)

    results = []
    for end_idx in range(years - 1, n):
        prod_value = rolling_prod.iloc[end_idx]
        if pd.isna(prod_value):
            continue
        cagr = prod_value ** (1 / years) - 1

        start_idx = end_idx - years + 1
        start_date = df.loc[start_idx, "report_date"]
        end_date = df.loc[end_idx, "report_date"]

        results.append({
            "start_date": start_date,
            "end_date": end_date,
            "start_year": int(start_date.year),
            "end_year": int(end_date.year),
            f"cagr_returns_{years}_years": round(float(cagr), 4)
        })

    return pd.DataFrame(results).sort_values("end_date").reset_index(drop=True)

unit_map = {
    "trillion": 1e12,
    "billion": 1e9,
    "million": 1e6,
    "thousand": 1e3
}