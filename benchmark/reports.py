"""Markdown report rendering for benchmark archives."""

from datetime import datetime
from pathlib import Path
import json

from records import unpack_comparison, unpack_reports, validate_archive_reports


TEMPLATE = """# {archive_name}: Stock Price Cold Query ({tag})

## Environment

| Item | Value |
| --- | --- |
| Date / OS | {date_os} |
| CPU / RAM | {cpu_ram} |
| Python / DuckDB / pandas | {py_duck_pandas} |
| cache_httpfs / httpfs | {ext_versions} |
| Threads / memory limit | {threads_mem} |
| HTTP proxy / keep-alive | {proxy_keepalive} |
| Reader | {reader} |
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

| Symbol | Rows | {trial_headers} | Median (s) | Sample std (s) |
| --- | ---: | {trial_align} | ---: | ---: |
{result_rows}

### Timing Breakdown (Median Run, {breakdown_symbol})

| Phase | Time (s) | % of E2E |
| --- | ---: | ---: |
| Process startup | {proc_start:.3f} | {proc_start_pct:.1f}% |
| DuckDB init + extension load | {init_sec:.3f} | {init_pct:.1f}% |
{resolve_row}| Data query + materialization | {query_sec:.3f} | {query_pct:.1f}% |
| **Total (E2E)** | **{median_sec:.3f}** | **100%** |
{resolve_note}
### Cache Footprint

| Symbol | Cache Files | Cache Bytes |
| --- | ---: | ---: |
{cache_rows}
{cache_note}
### Result Checksums

{checksum_rows}

All {total_trials} trials succeeded; checksums matched across trials for each symbol.
{checksum_guidance}

Raw results: [archive JSON](./{archive_name}.json)
"""


def _format_bytes(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


def _extract_run_date(report: dict) -> str:
    """Return the UTC run date encoded in the benchmark identifier."""
    identifier = report.get("suite_id") or report.get("run_id", "")
    timestamp = identifier.split("_", 1)[0]
    try:
        return datetime.strptime(timestamp, "%Y%m%dT%H%M%S.%fZ").strftime("%Y-%m-%d")
    except ValueError:
        return "unknown"


def _extract_env_info(environment: dict, run_date: str) -> dict:
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
        "date_os": f"{run_date} / {platform_str}, {machine}",
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


def _render_single_markdown(reports, archive_json_path: Path, output_md_path: Path) -> None:
    """Render a legacy standalone run report."""
    validate_archive_reports(reports)

    # Use first report for shared metadata
    first = reports[0]
    env_info = _extract_env_info(first["environment"], _extract_run_date(first))
    settings_info = _extract_settings_info(first["configured_settings"])

    # Dataset info
    dataset = "defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet"
    revision = first.get("revision", "unknown")
    tag = first.get("tag", "unknown")

    # Symbols and runs
    symbols = first.get("suite_symbols", [])
    runs = first.get("requested_runs", 3)
    default_symbols = ", ".join(symbols)

    # Resolve-direct uses an exact read_parquet file list so cache_httpfs does
    # not interpret the signed query string as a glob.
    resolve_direct = bool(first.get("resolve_direct"))
    if resolve_direct:
        reader = "cache_httpfs via signed CDN URL (resolve-once per trial; exact file list)"
        cache_note = (
            "_Cache footprint is measured within one trial. cache_httpfs keys the full signed URL, "
            "so cached blocks are not reused after the signature changes._\n"
        )
        checksum_guidance = (
            "Compare `sha256` against the paired pinned baseline archive to verify identical results."
        )
    else:
        reader = "cache_httpfs (on-disk)"
        cache_note = ""
        checksum_guidance = "Use these checksums as the pinned baseline for paired experiments."

    # Build a faithful reproduction command from the archived record.
    configured_settings = first["configured_settings"]
    proxy = configured_settings.get("http_proxy", "")
    proxy_flag = f' --http-proxy "{proxy}"' if "http_proxy" in configured_settings else ""
    keep_alive = bool(first["configured_settings"].get("http_keep_alive", False))
    keep_flag = " --keep-alive" if keep_alive else ""
    resolve_flag = " --resolve-direct" if resolve_direct else ""
    symbol_flag = f" --symbol {symbols[0]}" if len(symbols) == 1 else ""
    timeout_flag = f" --timeout {first.get('timeout_seconds', 600)}"
    run_cmd = (f'.venv/bin/python benchmark/bench.py run --runs {runs} --tag {tag}'
               f'{symbol_flag}{proxy_flag}{keep_flag}{resolve_flag}{timeout_flag}'
               f' --revision {revision}')

    # Cold state description
    cold_state = first.get("methodology", {}).get("cold", "Fresh process and empty data cache per trial")
    if resolve_direct:
        cold_state += "; resolve-once HEAD included in query time"

    # Per-symbol statistics
    result_rows = []
    cache_rows = []
    checksum_rows = []
    all_trials = 0
    # Timing breakdown from first symbol's median run
    breakdown = {}
    trial_headers = " | ".join(f"Trial {i + 1} (s)" for i in range(runs))
    trial_align = " | ".join(["---:"] * runs)

    for report in reports:
        symbol = report["symbol"]
        stats = report["statistics"]

        samples = report["samples"]
        ok_samples = [s for s in samples if s["status"] == "ok"]
        all_trials += len(ok_samples)

        # Trial times
        trial_times = [f"{s['e2e_seconds']:.6f}" for s in ok_samples]
        while len(trial_times) < runs:
            trial_times.append("—")

        median_sec = stats["median_seconds"]
        std_sec = stats.get("std_seconds") or 0
        rows = ok_samples[0]["result"]["rows"] if ok_samples else 0
        sha = ok_samples[0]["result"].get("sha256", "—") if ok_samples else "—"

        result_rows.append(
            f"| {symbol} | {rows:,} | {' | '.join(trial_times)} | **{median_sec:.6f}** | {std_sec:.6f} |"
        )
        checksum_rows.append(f"| {symbol} | `{sha}` |")

        # Cache info from first ok sample
        if ok_samples:
            s0 = ok_samples[0]
            cache_files = s0.get("cache_files_after_query", 0)
            cache_bytes = s0.get("cache_bytes_after_query", 0)
            cache_rows.append(f"| {symbol} | {cache_files} | {_format_bytes(cache_bytes)} |")

        # Timing breakdown for median run of first symbol (or first report
        # with statistics when the archive predates suite metadata).
        if not breakdown and ok_samples and (not symbols or symbol == symbols[0]):
            median_sample = min(ok_samples, key=lambda s: abs(s["e2e_seconds"] - median_sec))
            proc_start = median_sample.get("process_start_seconds", 0)
            init_sec = median_sample.get("initialization_seconds", 0)
            query_sec = median_sample.get("query_seconds", 0)
            resolve_sec = median_sample.get("resolve_seconds") or 0
            total = median_sec

            breakdown = {
                "breakdown_symbol": symbol,
                "proc_start": proc_start,
                "proc_start_pct": (proc_start / total * 100) if total else 0,
                "init_sec": init_sec,
                "init_pct": (init_sec / total * 100) if total else 0,
                "resolve_row": (
                    f"| URL resolve (fresh signed CDN URL) | {resolve_sec:.3f} | {(resolve_sec / total * 100) if total else 0:.1f}% |\n"
                    if resolve_sec else ""
                ),
                "resolve_note": (
                    "_Resolve is included in data-query time above; "
                    f"net data query is {query_sec - resolve_sec:.3f} s._\n"
                    if resolve_sec else ""
                ),
                "query_sec": query_sec - resolve_sec if resolve_sec else query_sec,
                "query_pct": ((query_sec - resolve_sec) / total * 100) if total else 0,
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
        tag=tag,
        **env_info,
        **settings_info,
        reader=reader,
        dataset=dataset,
        revision=revision,
        samples_desc=samples_desc,
        cold_state=cold_state,
        run_cmd=run_cmd,
        default_symbols=default_symbols,
        runs=runs,
        trial_headers=trial_headers,
        trial_align=trial_align,
        result_rows="\n".join(result_rows),
        cache_rows="\n".join(cache_rows),
        cache_note=cache_note,
        checksum_rows="| Symbol | SHA256 |\n| --- | --- |\n" + "\n".join(checksum_rows),
        checksum_guidance=checksum_guidance,
        total_trials=all_trials,
        **breakdown,
    )

    output_md_path.write_text(md, encoding="utf-8")
    print(f"Report: {output_md_path}")


COMPARISON_TEMPLATE = """# {archive_name}: Stock Price Cold Query Comparison

## Environment

| Item | Value |
| --- | --- |
| Run dates | baseline {baseline_date} / candidate {candidate_date} |
| OS / machine | {platform}, {machine} |
| CPU / RAM | {cpu_ram} |
| Python / DuckDB / pandas | {py_duck_pandas} |
| cache_httpfs / httpfs | {ext_versions} |
| Threads / memory limit | {threads_mem} |
| HTTP proxy / keep-alive | {proxy_keepalive} |
| Baseline reader | {baseline_reader} |
| Candidate reader | {candidate_reader} |
| Dataset | {dataset} |
| Revision | {revision} |
| Symbols | {symbols} |
| Cold state | {cold_state} |
| Declared setting differences | {setting_differences} |

## Reproduce

From the project root (dependencies and extensions already installed):

Baseline:

```bash
{baseline_command}
```

Candidate:

```bash
{candidate_command}
```

## Result

| Symbol | Rows | Baseline trials (s) | Candidate trials (s) | Baseline median | Candidate median | Change |
| --- | ---: | --- | --- | ---: | ---: | ---: |
{result_rows}

### Timing Breakdown (Median Run, {breakdown_symbol})

| Phase | Baseline (s) | Candidate (s) |
| --- | ---: | ---: |
| Process startup | {baseline_process:.3f} | {candidate_process:.3f} |
| DuckDB init + extension load | {baseline_init:.3f} | {candidate_init:.3f} |
| URL resolve | {baseline_resolve:.3f} | {candidate_resolve:.3f} |
| Data query + materialization | {baseline_query:.3f} | {candidate_query:.3f} |
| **Total (E2E)** | **{baseline_total:.3f}** | **{candidate_total:.3f}** |

### Cache Footprint

| Symbol | Baseline files / bytes | Candidate files / bytes |
| --- | ---: | ---: |
{cache_rows}

### Result Checksums

| Symbol | Rows | SHA256 |
| --- | ---: | --- |
{checksum_rows}

All {total_trials} baseline and candidate trials succeeded. Result hashes match
for every symbol.

## Cache-Key Limitation

The candidate keeps `cache_httpfs`, but the extension keys cached blocks by the
complete signed URL. Observed Hugging Face URLs were valid for approximately
60 minutes, while the production client uses a conservative 30-minute resolve
TTL. Blocks are reused while that exact URL remains active and are not
addressable after a process restart or signature change. Old blocks remain on
disk until normal invalidation or eviction.

## Interpretation

This is an isolated cold-data-cache benchmark, not a machine-cold benchmark.
OS code pages, DNS, proxy behavior, and remote CDN caches remain uncontrolled.
Treat the medians as directional evidence rather than a latency SLA.

Raw paired results: [archive JSON](./{archive_name}.json)
"""


def _reader_name(report):
    if report.get("resolve_direct"):
        return "cache_httpfs via signed CDN URL (resolve-once; exact file list)"
    return "cache_httpfs via pinned Hugging Face URL"


def _run_command(report):
    settings = report.get("configured_settings", {})
    proxy_flag = (
        f' --http-proxy "{settings.get("http_proxy", "")}"'
        if "http_proxy" in settings else ""
    )
    keep_flag = " --keep-alive" if settings.get("http_keep_alive") else ""
    resolve_flag = " --resolve-direct" if report.get("resolve_direct") else ""
    symbols = report.get("suite_symbols", [])
    symbol_flag = f" --symbol {symbols[0]}" if len(symbols) == 1 else ""
    return (
        f'.venv/bin/python benchmark/bench.py run --runs {report.get("requested_runs", 3)}'
        f' --tag {report.get("tag", "unknown")}{symbol_flag}{proxy_flag}{keep_flag}'
        f'{resolve_flag} --timeout {report.get("timeout_seconds", 600)}'
        f' --revision {report.get("revision", "unknown")}'
    )


def _median_breakdown(report):
    samples = [sample for sample in report["samples"] if sample["status"] == "ok"]
    median = report["statistics"]["median_seconds"]
    sample = min(samples, key=lambda item: abs(item["e2e_seconds"] - median))
    resolve = sample.get("resolve_seconds") or 0
    query = sample.get("query_seconds", 0)
    return {
        "process": sample.get("process_start_seconds", 0),
        "init": sample.get("initialization_seconds", 0),
        "resolve": resolve,
        "query": query - resolve,
        "total": median,
    }


def _render_comparison_markdown(record, archive_json_path: Path,
                                output_md_path: Path) -> None:
    baseline_reports, candidate_reports = unpack_comparison(record)
    baseline_first = baseline_reports[0]
    candidate_first = candidate_reports[0]
    environment = baseline_first["environment"]
    env_info = _extract_env_info(environment, _extract_run_date(candidate_first))
    settings_info = _extract_settings_info(baseline_first["configured_settings"])

    baseline_by_symbol = {report["symbol"]: report for report in baseline_reports}
    candidate_by_symbol = {report["symbol"]: report for report in candidate_reports}
    symbols = baseline_first.get("suite_symbols") or list(baseline_by_symbol)
    result_rows = []
    cache_rows = []
    checksum_rows = []
    for symbol in symbols:
        baseline = baseline_by_symbol[symbol]
        candidate = candidate_by_symbol[symbol]
        baseline_samples = [sample for sample in baseline["samples"] if sample["status"] == "ok"]
        candidate_samples = [sample for sample in candidate["samples"] if sample["status"] == "ok"]
        baseline_median = baseline["statistics"]["median_seconds"]
        candidate_median = candidate["statistics"]["median_seconds"]
        change = (candidate_median / baseline_median - 1) * 100
        rows = baseline_samples[0]["result"]["rows"]
        baseline_trials = ", ".join(f'{sample["e2e_seconds"]:.6f}' for sample in baseline_samples)
        candidate_trials = ", ".join(f'{sample["e2e_seconds"]:.6f}' for sample in candidate_samples)
        result_rows.append(
            f"| {symbol} | {rows:,} | {baseline_trials} | {candidate_trials} | "
            f"{baseline_median:.6f} | **{candidate_median:.6f}** | {change:+.1f}% |"
        )
        baseline_sample = baseline_samples[0]
        candidate_sample = candidate_samples[0]
        cache_rows.append(
            f'| {symbol} | {baseline_sample.get("cache_files_after_query", 0)} / '
            f'{_format_bytes(baseline_sample.get("cache_bytes_after_query", 0))} | '
            f'{candidate_sample.get("cache_files_after_query", 0)} / '
            f'{_format_bytes(candidate_sample.get("cache_bytes_after_query", 0))} |'
        )
        checksum_rows.append(
            f'| {symbol} | {rows:,} | `{baseline_sample["result"].get("sha256", "—")}` |'
        )

    breakdown_symbol = symbols[0]
    baseline_breakdown = _median_breakdown(baseline_by_symbol[breakdown_symbol])
    candidate_breakdown = _median_breakdown(candidate_by_symbol[breakdown_symbol])
    differences = []
    if baseline_first.get("resolve_direct") != candidate_first.get("resolve_direct"):
        differences.append(
            f'`resolve_direct`: {str(bool(baseline_first.get("resolve_direct"))).lower()} '
            f'→ {str(bool(candidate_first.get("resolve_direct"))).lower()}'
        )
    for name in record.get("allowed_setting_differences", []):
        baseline_value = baseline_first.get("configured_settings", {}).get(name)
        candidate_value = candidate_first.get("configured_settings", {}).get(name)
        differences.append(f'`{name}`: `{baseline_value}` → `{candidate_value}`')
    setting_differences = "; ".join(differences) or "none"
    total_trials = sum(
        len(report["samples"])
        for report in baseline_reports + candidate_reports
    )
    extensions = " / ".join(
        f'{item["name"]} {item["version"]}'
        for item in environment.get("extensions", [])
    ) or "unknown"

    md = COMPARISON_TEMPLATE.format(
        archive_name=archive_json_path.stem,
        baseline_date=_extract_run_date(baseline_first),
        candidate_date=_extract_run_date(candidate_first),
        platform=environment.get("platform", "unknown"),
        machine=environment.get("machine", "unknown"),
        cpu_ram=env_info["cpu_ram"],
        py_duck_pandas=env_info["py_duck_pandas"],
        ext_versions=extensions,
        threads_mem=settings_info["threads_mem"],
        proxy_keepalive=settings_info["proxy_keepalive"],
        baseline_reader=_reader_name(baseline_first),
        candidate_reader=_reader_name(candidate_first),
        dataset="defeatbeta/yahoo-finance-data, data/US/stock_prices.parquet",
        revision=baseline_first.get("revision", "unknown"),
        symbols=", ".join(symbols),
        cold_state=baseline_first.get("methodology", {}).get("cold", "unknown"),
        setting_differences=setting_differences,
        baseline_command=_run_command(baseline_first),
        candidate_command=_run_command(candidate_first),
        result_rows="\n".join(result_rows),
        breakdown_symbol=breakdown_symbol,
        baseline_process=baseline_breakdown["process"],
        candidate_process=candidate_breakdown["process"],
        baseline_init=baseline_breakdown["init"],
        candidate_init=candidate_breakdown["init"],
        baseline_resolve=baseline_breakdown["resolve"],
        candidate_resolve=candidate_breakdown["resolve"],
        baseline_query=baseline_breakdown["query"],
        candidate_query=candidate_breakdown["query"],
        baseline_total=baseline_breakdown["total"],
        candidate_total=candidate_breakdown["total"],
        cache_rows="\n".join(cache_rows),
        checksum_rows="\n".join(checksum_rows),
        total_trials=total_trials,
    )
    output_md_path.write_text(md, encoding="utf-8")
    print(f"Report: {output_md_path}")


def render_markdown(archive_json_path: Path, output_md_path: Path) -> None:
    """Render either a legacy standalone run or a paired comparison."""
    record = json.loads(archive_json_path.read_text(encoding="utf-8"))
    if record.get("format_version") == 3:
        _render_comparison_markdown(record, archive_json_path, output_md_path)
        return
    reports = unpack_reports(record)
    _render_single_markdown(reports, archive_json_path, output_md_path)
