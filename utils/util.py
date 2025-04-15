import psutil
import re
import os

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
    if os.name == "nt":
        temp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Temp"
    else:
        temp_dir = "/tmp"
    cache_dir = os.path.join(temp_dir, name)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir
