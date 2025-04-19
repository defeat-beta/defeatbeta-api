from typing import List, Dict
import json

import psutil
import re
import os
import platform
import tempfile

from data.finance_item import FinanceItem

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

def validate_httpfs_cache_directory(name: str) -> str:
    if platform.system() in ("Darwin", "Linux"):
        temp_dir = "/tmp"
    else:
        temp_dir = tempfile.gettempdir()
    cache_dir = os.path.join(temp_dir, name)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


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
            spec=item["spec"],
            ref=item["ref"],
            industry=item.get("industry")
        )
        result.append(finance_item)
    return result
