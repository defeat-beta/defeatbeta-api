"""Versioned workload contract, independent of the measured product revision."""

import hashlib
import json
import random

from benchmark.common import API_FILES, SYMBOLS


SUITE_VERSION = 2
METHODS = (*API_FILES, "quarterly_income_statement", "quarterly_balance_sheet",
           "quarterly_cash_flow", "quarterly_revenue_by_breakdown", "market_capitalization",
           "ttm_pe", "beta", "transcripts_list", "transcript_body", "news_list", "news_body")
MIXED = ("price", "info", "shares", "sec_filing")
STATES = ("first_use", "memory_warm", "disk_warm")
ISOLATED_STATES = ("first_use", "metadata_ready", "memory_warm", "disk_warm")
CACHE_POLICIES = ("default", "project-only")


def make_suite(name="release", seed=1729, cache_policy="default"):
    if name not in ("smoke", "release"):
        raise ValueError("Unknown suite")
    if cache_policy not in CACHE_POLICIES:
        raise ValueError("Unknown cache policy")
    symbols = list(SYMBOLS)
    random.Random(seed).shuffle(symbols)
    cases = []
    methods = ("price", "info", "market_capitalization", "transcript_body") if name == "smoke" else METHODS
    states = (("first_use", "memory_warm") if name == "smoke" else
              STATES if cache_policy == "default" else ISOLATED_STATES)
    # Rotate coverage across the predeclared corpus; do not choose favorable timings.
    for index, method in enumerate(methods):
        selected = symbols[index % len(symbols)]
        for state in states:
            cases.append({"id": f"{method}.{state}", "kind": "single", "state": state,
                          "tasks": [{"symbol": selected, "method": method}], "concurrency": 1})
    concurrencies = (1, 4) if name == "smoke" else (1, 4, 16, 64, 128)
    plan = [{"symbol": symbol, "method": method} for symbol in symbols for method in MIXED]
    batch_state = "first_use" if cache_policy == "default" else "metadata_ready"
    for concurrency in concurrencies:
        for pattern in ("burst", "stream"):
            # The stream executes identical work at every concurrency. Burst size is N.
            tasks = plan[:concurrency] if pattern == "burst" else plan[:8 if name == "smoke" else len(plan)]
            cases.append({"id": f"mixed.{pattern}.{concurrency}", "kind": pattern,
                          "state": batch_state, "tasks": tasks, "concurrency": concurrency})
    for case in cases:
        case["cache_policy"] = cache_policy
    suite = {"version": SUITE_VERSION, "name": name, "seed": seed, "symbols": symbols,
             "methods": list(methods), "cases": cases, "cache_policy": cache_policy,
             "corpus_policy": "Fixed cross-sector corpus with long/short histories, ADRs and sparse events; seeded order",
             "stream_policy": ("Fresh process with default caches; natural sharing/hits during the fixed plan"
                               if cache_policy == "default" else
                               "Cold project data and warm metadata; native file cache disabled"),
             "selection_policy": "Manifest frozen before either implementation is measured"}
    suite["sha256"] = hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest()
    return suite


def coverage(ticker_type):
    measured = set(METHODS) - {"transcripts_list", "transcript_body", "news_list", "news_body"}
    measured.update(("earning_call_transcripts", "news"))
    return {name: ("measured" if name in measured else
                   "excluded: presentation/export/AI" if name in ("dcf", "download_data_performance") else
                   "not measured: related query path represented; no API-specific performance claim")
            for name in sorted(dir(ticker_type)) if not name.startswith("_") and callable(getattr(ticker_type, name))}


def invoke(ticker, task):
    method = task["method"]
    if method == "transcripts_list":
        return ticker.earning_call_transcripts().get_transcripts_list()
    if method == "transcript_body":
        return ticker.earning_call_transcripts().get_transcript(task["fiscal_year"], task["fiscal_quarter"])
    if method == "news_list":
        return ticker.news().get_news_list()
    if method == "news_body":
        return ticker.news().get_news(task["uuid"])
    result = getattr(ticker, method)()
    return result.df() if hasattr(result, "df") else result
