"""Small measurement primitives; importing this module never imports the product."""

from datetime import date, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics


ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("PDD", "BABA", "KDP", "ZTS", "AAPL", "MSFT", "AMZN", "NVDA",
           "META", "GOOG", "TSLA", "JPM", "V", "MA", "WMT", "COST",
           "UNH", "XOM", "JNJ", "PG", "HD", "BAC", "ABBV", "KO",
           "PEP", "AVGO", "ORCL", "NFLX", "CRM", "AMD", "DIS", "INTC")
API_FILES = dict(zip(
    ("price", "info", "sec_filing", "officers", "calendar", "splits", "dividends", "ttm_eps", "shares"),
    ("stock_prices", "stock_profile", "stock_sec_filing", "stock_officers", "stock_earning_calendar",
     "stock_split_events", "stock_dividend_events", "stock_tailing_eps", "stock_shares_outstanding")))


def redact_secrets(value):
    if isinstance(value, dict):
        return {str(key): redact_secrets(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]+", r"\1?<redacted>", value)
    return re.sub(r"((?:https?|socks5h?)://)[^/@\s]+@", r"\1<redacted>@", value)


def save_json(path, value):
    path = Path(path)
    content = json.dumps(redact_secrets(value), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def percentile(values, fraction):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def distribution(values):
    return {"samples": len(values), "total_seconds": sum(values),
            "p50_seconds": statistics.median(values) if values else None,
            "p95_seconds": percentile(values, .95), "max_seconds": max(values) if values else None}


def canonical(value):
    """Normalize representations without rounding numeric differences away."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if hasattr(value, "tolist"):
        return canonical(value.tolist())
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (str, bool, int)):
        return value
    return str(value)


def result_fingerprint(frame):
    """Hash the full row multiset and column names, retaining duplicate rows."""
    columns = [str(name) for name in frame.columns]
    rows = sorted(json.dumps(canonical(row), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                  for row in frame.itertuples(index=False, name=None))
    digest = hashlib.sha256(json.dumps(columns).encode())
    for row in rows:
        digest.update(b"\n" + row.encode())
    return {"rows": len(frame), "columns": columns, "sha256": digest.hexdigest()}


def source_hashes(root=ROOT):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((Path(root) / "defeatbeta_api").rglob("*"))
            if path.is_file() and path.suffix in (".py", ".sql", ".json", ".md", ".html")}


def environment_info():
    import psutil
    from importlib.metadata import version
    from urllib.request import getproxies

    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count(),
            "ram_bytes": psutil.virtual_memory().total,
            "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
            "dependencies": {name: version(name) for name in ("duckdb", "httpx", "httpcore", "h2", "pandas", "fsspec")},
            "proxies": redact_secrets({key: value for key, value in getproxies().items() if key != "no"})}
