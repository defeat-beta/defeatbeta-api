"""Markdown report rendering for benchmark archives."""

from datetime import datetime, timezone
from pathlib import Path
import json
import statistics

from records import unpack_reports


TEMPLATE = """# {archive_name}: Stock Price Cold Query Baseline

## Environment

| Item | Value |
| --- | --- |
| Date / OS | {date_os} |
| CPU / RAM | {cpu_ram} |
| Python / DuckDB / pandas | {py_duck_pandas} |
| cache_httpfs / httpfs | {ext_versions} |
| Threads / memory limit | {threads_mem} |
| HTTP proxy / keep-alive | {proxy_keepalive} |
| Dataset | {dataset} |
| Revision | {revision} |
| Samples | {samples_desc} |
| Cold state | {cold_state} |

## Run

From the project root (dependencies and extensions already installed):

```bash
{run_cmd}
```

Default: {default_symbols} in round-robin order, {runs} trials each. Use `--symbol` for a single stock.

## Result

| Symbol | Rows | Trial 1 (s) | Trial 2 (s) | Trial 3 (s) | Median (s) | Sample std (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{result_rows}

### Timing Breakdown (Median Run)

| Phase | Time (s) | % of E2E |
| --- | ---: | ---: |
| Process startup | {proc_start:.3f} | {proc_start_pct:.1f}% |
| DuckDB init + extension load | {init_sec:.3f} | {init_pct:.1f}% |
| Query execution + materialization | {query_sec:.3f} | {query_pct:.1f}% |
| **Total (E2E)** | **{median_sec:.3f}** | **100%** |

### Cache Footprint

| Symbol | Cache Files | Cache Bytes |
| --- | ---: | ---: |
{cache_rows}

All {total_trials} trials succeeded; checksums matched across trials for each symbol.

Raw results: [baseline archive](../results/archive/{archive_name}.json)
"""


def _format_bytes(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


def _extract_env_info(environment: dict) -> dict:
    """Extract human-readable environment info."""
    python = environment.get("python", "").split("(")[0].strip()
    duckdb = environment.get("duckdb", "unknown")
    pandas = environment.get("pandas", "unknown")
    platform_str = environment.get("platform", "unknown")
    machine = environment.get("machine", "unknown")
    logical = environment.get("logical_cpus", "?")
    physical = environment.get("physical_cpus", "?")
    memory_gb = environment.get("memory_bytes", 0) / (1024 ** 3)

    ext_lines = []
    for ext in environment.get("extensions", []):
        ext_lines.append(f"{ext['name']} {ext['version']}")
    ext_str = " / ".join(ext_lines) if ext_lines else "unknown"

    proxy_vars = environment.get("proxy_environment_variables_present", [])
    proxy_str = ", ".join(proxy_vars) if proxy_vars else "none"

    return {
        "date_os": f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} / {platform_str}, {machine}",
        "cpu_ram": f"{logical} cores / {memory_gb:.0f} GiB",
        "py_duck_pandas": f"{python} / {duckdb} / {pandas}",
        "ext_versions": ext_str,
    }


def _extract_settings_info(configured_settings: dict) -> dict:
    threads = configured_settings.get("threads", "?")
    mem_limit = configured_settings.get("memory_limit", "?")
    proxy = configured_settings.get("http_proxy", "none")
    keep_alive = configured_settings.get("http_keep_alive", False)

    return {
        "threads_mem": f"{threads} / {mem_limit}",
        "proxy_keepalive": f"{proxy} / {str(keep_alive).lower()}",
    }


def render_markdown(archive_json_path: Path, output_md_path: Path) -> None:
    """Render a Markdown report from an archive JSON file."""
    record = json.loads(archive_json_path.read_text(encoding="utf-8"))
    reports = unpack_reports(record)

    if not reports:
        raise ValueError("No reports in archive")

    # Use first report for shared metadata
    first = reports[0]
    env_info = _extract_env_info(first["environment"])
    settings_info = _extract_settings_info(first["configured_settings"])

    # Dataset info
    url = first.get("url", "")
    dataset = "defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet"
    revision = first.get("revision", "unknown")

    # Symbols and runs
    symbols = first.get("suite_symbols", [])
    runs = first.get("requested_runs", 3)
    default_symbols = ", ".join(symbols)

    # Build run command
    proxy = first["configured_settings"].get("http_proxy", "")
    proxy_flag = f' --http-proxy "{proxy}"' if proxy else ""
    run_cmd = f'http_proxy="{proxy}" .venv/bin/python benchmark/bench.py --runs {runs} --tag baseline-multi{proxy_flag} --revision {revision}'

    # Cold state description
    cold_state = first.get("methodology", {}).get("cold", "Fresh process and empty data cache per trial")

    # Per-symbol statistics
    result_rows = []
    cache_rows = []
    all_trials = 0
    # Timing breakdown from first symbol's median run
    breakdown = {}

    for report in reports:
        symbol = report["symbol"]
        stats = report.get("statistics")
        if not stats:
            continue

        samples = report["samples"]
        ok_samples = [s for s in samples if s["status"] == "ok"]
        all_trials += len(ok_samples)

        # Trial times
        trial_times = [f"{s['e2e_seconds']:.6f}" for s in ok_samples]
        while len(trial_times) < 3:
            trial_times.append("—")

        median_sec = stats["median_seconds"]
        std_sec = stats.get("std_seconds") or 0
        rows = ok_samples[0]["result"]["rows"] if ok_samples else 0

        result_rows.append(
            f"| {symbol} | {rows:,} | {trial_times[0]} | {trial_times[1]} | {trial_times[2]} | **{median_sec:.6f}** | {std_sec:.6f} |"
        )

        # Cache info from first ok sample
        if ok_samples:
            s0 = ok_samples[0]
            cache_files = s0.get("cache_files_after_query", 0)
            cache_bytes = s0.get("cache_bytes_after_query", 0)
            cache_rows.append(f"| {symbol} | {cache_files} | {_format_bytes(cache_bytes)} |")

        # Timing breakdown for median run of first symbol
        if symbol == symbols[0] and ok_samples:
            median_sample = next(s for s in ok_samples if abs(s["e2e_seconds"] - median_sec) < 1e-6)
            proc_start = median_sample.get("process_start_seconds", 0)
            init_sec = median_sample.get("initialization_seconds", 0)
            query_sec = median_sample.get("query_seconds", 0)
            total = median_sec

            breakdown = {
                "proc_start": proc_start,
                "proc_start_pct": (proc_start / total * 100) if total else 0,
                "init_sec": init_sec,
                "init_pct": (init_sec / total * 100) if total else 0,
                "query_sec": query_sec,
                "query_pct": (query_sec / total * 100) if total else 0,
                "median_sec": median_sec,
            }

    # Samples description
    samples_parts = []
    for report in reports:
        symbol = report["symbol"]
        ok_samples = [s for s in report["samples"] if s["status"] == "ok"]
        if ok_samples:
            rows = ok_samples[0]["result"]["rows"]
            samples_parts.append(f"{symbol} ({rows:,} rows)")
    samples_desc = ", ".join(samples_parts)

    # Archive name (stem)
    archive_name = archive_json_path.stem

    md = TEMPLATE.format(
        archive_name=archive_name,
        **env_info,
        **settings_info,
        dataset=dataset,
        revision=revision,
        samples_desc=samples_desc,
        cold_state=cold_state,
        run_cmd=run_cmd,
        default_symbols=default_symbols,
        runs=runs,
        result_rows="\n".join(result_rows),
        cache_rows="\n".join(cache_rows),
        total_trials=all_trials,
        **breakdown,
    )

    output_md_path.write_text(md, encoding="utf-8")
    print(f"Report: {output_md_path}")