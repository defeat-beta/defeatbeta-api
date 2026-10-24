"""Freeze sampled symbols, every query operation, and one Cartesian workload."""

from copy import deepcopy
import hashlib
import inspect
import json


PLAN_VERSION = 1
SAMPLE_SYMBOLS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "WMT")
EXCLUSIONS = {"dcf": "Excel export", "download_data_performance": "Diagnostic output"}
WRAPPER_METHODS = ("earning_call_transcripts", "news")
WRAPPERS = {
    "transcripts_list": "earning_call_transcripts.get_transcripts_list",
    "transcript_body": "earning_call_transcripts.get_transcript",
    "news_list": "news.get_news_list", "news_body": "news.get_news",
}
CONCURRENCIES = (1, 4, 16, 64, 128)


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def query_methods(ticker_type):
    methods = {}
    for name, method in inspect.getmembers(ticker_type, callable):
        if name.startswith("_") or name in EXCLUSIONS or name in WRAPPER_METHODS:
            continue
        kwargs = {}
        for parameter in inspect.signature(method).parameters.values():
            if parameter.name == "self":
                continue
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                raise ValueError(f"Declare benchmark parameters for {name}: {parameter.name}")
            if parameter.default is not parameter.empty:
                kwargs[parameter.name] = parameter.default
            elif name == "currency" and parameter.name == "symbol":
                kwargs["symbol"] = "EUR=X"
            else:
                raise ValueError(f"Declare benchmark parameters for {name}: {parameter.name}")
        methods[name] = {"call": name, "kwargs": kwargs}
    public = set(dir(ticker_type))
    for operation, call in WRAPPERS.items():
        if call.split(".")[0] in public:
            methods[operation] = {"call": call, "kwargs": {}}
    return dict(sorted(methods.items()))


def select_sample(companies):
    by_symbol = {}
    for company in companies:
        symbol = company.get("symbol", company.get("ticker"))
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("Catalog entries must identify a ticker")
        if symbol in by_symbol:
            raise ValueError(f"Duplicate catalog ticker: {symbol}")
        by_symbol[symbol] = company
    missing = set(SAMPLE_SYMBOLS) - set(by_symbol)
    if missing:
        raise ValueError(f"Fixed sample is missing catalog tickers: {sorted(missing)}")
    return [deepcopy(by_symbol[symbol]) for symbol in SAMPLE_SYMBOLS]


def build_plan(companies, methods, *, bodies=None, dataset=None, cache_capacity_bytes=2**60):
    if not companies or not methods:
        raise ValueError("The workload needs tickers and query methods")
    symbols = [company.get("symbol", company.get("ticker")) for company in companies]
    if any(not isinstance(symbol, str) or not symbol for symbol in symbols):
        raise ValueError("Invalid ticker")
    if len(symbols) != len(set(symbols)):
        raise ValueError("Duplicate ticker")
    if type(cache_capacity_bytes) is not int or cache_capacity_bytes < 1:
        raise ValueError("Cache capacity must be positive")
    currencies = {company.get("symbol", company.get("ticker")):
                  company.get("financial_currency") for company in companies}
    value = {"version": PLAN_VERSION, "symbols": sorted(symbols), "methods": deepcopy(methods),
             "currencies": currencies, "bodies": deepcopy(bodies or {}),
             "dataset": deepcopy(dataset or {}), "cache_capacity_bytes": cache_capacity_bytes,
             "task_count": len(symbols) * len(methods), "exclusions": EXCLUSIONS.copy(),
             "cache_policy": "Identical generous capacity; local memory or disk hits"}
    value["sha256"] = checksum(value)
    return value


def validate_plan(value):
    content = {key: item for key, item in value.items() if key != "sha256"}
    if value.get("version") != PLAN_VERSION or value.get("sha256") != checksum(content):
        raise ValueError("Workload identity changed")
    if (not value["symbols"] or not value["methods"]
            or value["symbols"] != sorted(set(value["symbols"]))
            or value["task_count"] != len(value["symbols"]) * len(value["methods"])):
        raise ValueError("Incomplete Cartesian workload")


def tasks(value):
    for symbol in value["symbols"]:
        for method, specification in value["methods"].items():
            task = {"id": json.dumps([symbol, method], separators=(",", ":")),
                    "symbol": symbol, "method": method, "call": specification["call"],
                    "kwargs": deepcopy(specification["kwargs"])}
            if method == "currency":
                currency = value["currencies"].get(symbol)
                task["kwargs"]["symbol"] = currency + "=X" if currency and currency != "USD" else "EUR=X"
            if method in ("transcript_body", "news_body"):
                parameters = value["bodies"].get(symbol, {}).get(method)
                if parameters is None:
                    task["not_applicable"] = "No source record available during discovery"
                else:
                    task["kwargs"] = deepcopy(parameters)
            yield task
