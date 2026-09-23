"""Render benchmark JSON records without executing performance workloads."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics


def unpack_reports(record):
    if record.get("format_version") != 2:
        raise ValueError("Unsupported run record format")

    def decode(value):
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                return record["shared"][value["$ref"]]
            return {key: decode(item) for key, item in value.items()}
        return value

    return decode(record["runs"])


def unpack_comparison(record):
    if record.get("format_version") != 3:
        raise ValueError("Unsupported comparison record format")
    return unpack_reports(record["baseline"]), unpack_reports(record["candidate"])


def _run_date(report):
    identifier = report.get("suite_id") or report.get("run_id", "")
    try:
        return datetime.strptime(
            identifier.split("_", 1)[0], "%Y%m%dT%H%M%S.%fZ"
        ).strftime("%Y-%m-%d")
    except ValueError:
        return "unknown"


def _metric(report):
    return (
        report.get("primary_metric")
        or (report.get("statistics") or {}).get("metric")
        or "e2e_seconds"
    )


def _ok_samples(report):
    return [sample for sample in report.get("samples", []) if sample.get("status") == "ok"]


def _sample_value(sample, metric):
    if metric in sample:
        return float(sample[metric])
    if metric == "execute_query_seconds" and "query_seconds" in sample:
        return float(sample["query_seconds"])
    return float(sample["e2e_seconds"])


def _summary(report):
    metric = _metric(report)
    samples = _ok_samples(report)
    values = [_sample_value(sample, metric) for sample in samples]
    archived = report.get("statistics") or {}
    if archived.get("metric", metric) == metric and archived.get("median_seconds") is not None:
        return archived
    return {
        "metric": metric,
        "count": len(values),
        "median_seconds": statistics.median(values),
        "min_seconds": min(values),
        "max_seconds": max(values),
        "p95_seconds": None,
        "std_seconds": statistics.stdev(values) if len(values) > 1 else None,
    }


def _median_sample(report):
    metric = _metric(report)
    median = _summary(report)["median_seconds"]
    return min(_ok_samples(report), key=lambda sample: abs(_sample_value(sample, metric) - median))


def _phase(sample, event_name, legacy_name=None):
    performance = sample.get("performance", {})
    if event_name in performance:
        return float(performance[event_name].get("seconds", 0))
    if legacy_name:
        return float(sample.get(legacy_name, 0) or 0)
    return 0.0


def _event_phase(events, event_name):
    return sum(
        float(event.get("duration_ns", 0)) / 1e9
        for event in events
        if event.get("name") == event_name
    )


def _breakdown(report):
    sample = _median_sample(report)
    initialization_events = sample.get("initialization_performance", [])
    resolve = _phase(sample, "duckdb.resolve_url", "resolve_seconds")
    execute = float(sample.get("execute_query_seconds", sample.get("query_seconds", 0)) or 0)
    return {
        "process_start": float(sample.get("process_start_seconds", 0) or 0),
        "import": float(sample.get("import_seconds", 0) or 0),
        "ticker_init": float(
            sample.get("ticker_initialization_seconds", sample.get("initialization_seconds", 0)) or 0
        ),
        "connection_init": _event_phase(
            initialization_events, "duckdb.initialize_connection"
        ),
        "cache_validation": _event_phase(
            initialization_events, "duckdb.validate_httpfs_cache"
        ),
        "resolve": resolve,
        "rewrite": _phase(sample, "duckdb.rewrite_urls"),
        "cursor_open": _phase(sample, "duckdb.cursor.open"),
        "sql_dataframe": _phase(sample, "duckdb.sql_to_dataframe"),
        "cursor_close": _phase(sample, "duckdb.cursor.close"),
        "execute_query": execute,
        "duckdb_query": _phase(sample, "duckdb.query", "query_seconds"),
        "api_call": float(sample.get("api_call_seconds", sample.get("e2e_seconds", 0)) or 0),
        "worker_wall": float(sample.get("worker_wall_seconds", sample.get("e2e_seconds", 0)) or 0),
    }


def _format_seconds(value):
    return f"{value:.6f}"


def _format_bytes(value):
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.2f} MiB"
    if value >= 1024:
        return f"{value / 1024:.2f} KiB"
    return f"{value} B"


def _environment(report):
    environment = report.get("environment", {})
    extensions = " / ".join(
        f"{item.get('name', '?')} {item.get('version', '?')}"
        for item in environment.get("extensions", [])
    ) or "unknown"
    python = environment.get("python", "unknown").split("(")[0].strip()
    memory = environment.get("memory_bytes", 0) / (1024 ** 3)
    return {
        "date": _run_date(report),
        "platform": environment.get("platform", "unknown"),
        "machine": environment.get("machine", "unknown"),
        "cpu": environment.get("logical_cpus", "unknown"),
        "memory": f"{memory:.0f} GiB" if memory else "unknown",
        "versions": f"{python} / {environment.get('duckdb', 'unknown')} / {environment.get('pandas', 'unknown')}",
        "extensions": extensions,
    }


def _command(report):
    settings = report.get("configured_settings", {})
    symbols = report.get("suite_symbols", [])
    symbol = f" --symbol {symbols[0]}" if len(symbols) == 1 else ""
    proxy = settings.get("http_proxy")
    proxy_flag = f' --http-proxy "{proxy}"' if proxy else ""
    keep_alive = "" if settings.get("http_keep_alive", True) else " --no-keep-alive"
    resolve = "" if report.get("resolve_direct", True) else " --no-resolve-direct"
    executable = "benchmark/benchmark.py" if report.get("api_call") else "benchmark/bench.py"
    revision = (
        f" --revision {report['revision']}"
        if executable.endswith("bench.py") and report.get("revision") else ""
    )
    return (
        f".venv/bin/python {executable} run --runs {report.get('requested_runs', 3)} "
        f"--tag {report.get('tag', 'unknown')}{symbol}{proxy_flag}{keep_alive}{resolve}{revision}"
    )


def _cache_description(sample):
    after = sample.get("cache_after_query")
    if after:
        return f"{after.get('files', 0)} / {_format_bytes(after.get('bytes', 0))}"
    return (
        f"{sample.get('cache_files_after_query', 0)} / "
        f"{_format_bytes(sample.get('cache_bytes_after_query', 0))}"
    )


def _single_markdown(reports, archive_path):
    first = reports[0]
    env = _environment(first)
    metric = _metric(first)
    rows = []
    checksums = []
    cache_rows = []
    for report in reports:
        samples = _ok_samples(report)
        summary = _summary(report)
        trials = ", ".join(
            _format_seconds(_sample_value(sample, metric)) for sample in samples
        )
        result = samples[0].get("result", {})
        rows.append(
            f"| {report['symbol']} | {result.get('rows', 0):,} | {trials} | "
            f"**{summary['median_seconds']:.6f}** |"
        )
        checksums.append(
            f"| {report['symbol']} | `{result.get('sha256', 'unavailable')}` |"
        )
        cache_rows.append(
            f"| {report['symbol']} | {_cache_description(samples[0])} |"
        )
    breakdown = _breakdown(reports[0])
    method = first.get("methodology", {})
    return f"""# {archive_path.stem}: Stock Price Cold Query

## Environment

| Item | Value |
| --- | --- |
| Run date | {env['date']} |
| OS / machine | {env['platform']} / {env['machine']} |
| CPU / RAM | {env['cpu']} logical CPUs / {env['memory']} |
| Python / DuckDB / pandas | {env['versions']} |
| cache_httpfs / httpfs | {env['extensions']} |
| API workload | {first.get('api_call', 'legacy direct DuckDB workload')} |
| Primary metric | `{metric}` |
| Cold state | {method.get('cold', 'unknown')} |

## Reproduce

```bash
{_command(first)}
```

## Result

| Symbol | Rows | Trials (s) | Median (s) |
| --- | ---: | --- | ---: |
{chr(10).join(rows)}

### Median Sample Timing Breakdown ({reports[0]['symbol']})

| Phase | Seconds |
| --- | ---: |
| Process start | {breakdown['process_start']:.6f} |
| Package import | {breakdown['import']:.6f} |
| Ticker initialization | {breakdown['ticker_init']:.6f} |
| DuckDB connection initialization | {breakdown['connection_init']:.6f} |
| Cache validation | {breakdown['cache_validation']:.6f} |
| URL resolve | {breakdown['resolve']:.6f} |
| URL rewrite | {breakdown['rewrite']:.6f} |
| Cursor open | {breakdown['cursor_open']:.6f} |
| SQL execution and DataFrame materialization | {breakdown['sql_dataframe']:.6f} |
| Cursor close | {breakdown['cursor_close']:.6f} |
| **DuckDBClient._execute_query** | **{breakdown['execute_query']:.6f}** |
| DuckDBClient.query | {breakdown['duckdb_query']:.6f} |
| Ticker.price API call | {breakdown['api_call']:.6f} |
| Worker wall time | {breakdown['worker_wall']:.6f} |

### Cache Footprint

| Symbol | Files / bytes after query |
| --- | ---: |
{chr(10).join(cache_rows)}

### Result Checksums

| Symbol | SHA256 |
| --- | --- |
{chr(10).join(checksums)}

Raw results: [archive JSON](./{archive_path.name})
"""


def _comparison_markdown(record, archive_path):
    baseline_reports, candidate_reports = unpack_comparison(record)
    baseline_by_symbol = {report["symbol"]: report for report in baseline_reports}
    candidate_by_symbol = {report["symbol"]: report for report in candidate_reports}
    symbols = baseline_reports[0].get("suite_symbols") or list(baseline_by_symbol)
    metric = _metric(candidate_reports[0])
    rows = []
    checksums = []
    cache_rows = []
    for symbol in symbols:
        baseline = baseline_by_symbol[symbol]
        candidate = candidate_by_symbol[symbol]
        baseline_summary = _summary(baseline)
        candidate_summary = _summary(candidate)
        change = (
            candidate_summary["median_seconds"] / baseline_summary["median_seconds"] - 1
        ) * 100
        baseline_samples = _ok_samples(baseline)
        candidate_samples = _ok_samples(candidate)
        result = baseline_samples[0]["result"]
        rows.append(
            f"| {symbol} | {result.get('rows', 0):,} | "
            f"{baseline_summary['median_seconds']:.6f} | "
            f"**{candidate_summary['median_seconds']:.6f}** | {change:+.1f}% |"
        )
        checksums.append(
            f"| {symbol} | {result.get('rows', 0):,} | "
            f"`{result.get('sha256', 'unavailable')}` |"
        )
        cache_rows.append(
            f"| {symbol} | {_cache_description(baseline_samples[0])} | "
            f"{_cache_description(candidate_samples[0])} |"
        )

    baseline_breakdown = _breakdown(baseline_reports[0])
    candidate_breakdown = _breakdown(candidate_reports[0])
    env = _environment(candidate_reports[0])
    method = candidate_reports[0].get("methodology", {})
    breakdown_rows = []
    phase_labels = (
        ("process_start", "Process start"),
        ("import", "Package import"),
        ("ticker_init", "Ticker initialization"),
        ("connection_init", "DuckDB connection initialization"),
        ("cache_validation", "Cache validation"),
        ("resolve", "URL resolve"),
        ("rewrite", "URL rewrite"),
        ("cursor_open", "Cursor open"),
        ("sql_dataframe", "SQL execution and DataFrame materialization"),
        ("cursor_close", "Cursor close"),
        ("execute_query", "**DuckDBClient._execute_query**"),
        ("duckdb_query", "DuckDBClient.query"),
        ("api_call", "Ticker.price API call"),
        ("worker_wall", "Worker wall time"),
    )
    for key, label in phase_labels:
        breakdown_rows.append(
            f"| {label} | {baseline_breakdown[key]:.6f} | "
            f"{candidate_breakdown[key]:.6f} |"
        )

    return f"""# {archive_path.stem}: Stock Price Cold Query Comparison

## Environment

| Item | Value |
| --- | --- |
| Run dates | baseline {_run_date(baseline_reports[0])} / candidate {_run_date(candidate_reports[0])} |
| OS / machine | {env['platform']} / {env['machine']} |
| CPU / RAM | {env['cpu']} logical CPUs / {env['memory']} |
| Python / DuckDB / pandas | {env['versions']} |
| cache_httpfs / httpfs | {env['extensions']} |
| API workload | {candidate_reports[0].get('api_call', 'legacy direct DuckDB workload')} |
| Primary metric | `{metric}` |
| Cold state | {method.get('cold', 'unknown')} |
| Declared setting differences | {', '.join(record.get('allowed_setting_differences', [])) or 'none'} |

## Reproduce

Baseline:

```bash
{_command(baseline_reports[0])}
```

Candidate:

```bash
{_command(candidate_reports[0])}
```

## Result

| Symbol | Rows | Baseline median (s) | Candidate median (s) | Change |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

### Median Sample Timing Breakdown ({symbols[0]})

| Phase | Baseline (s) | Candidate (s) |
| --- | ---: | ---: |
{chr(10).join(breakdown_rows)}

### Cache Footprint

| Symbol | Baseline files / bytes | Candidate files / bytes |
| --- | ---: | ---: |
{chr(10).join(cache_rows)}

### Result Checksums

| Symbol | Rows | SHA256 |
| --- | ---: | --- |
{chr(10).join(checksums)}

## Interpretation

{method.get('main_metric', 'See the primary metric above.')} External DNS,
proxy, operating-system, and remote CDN state remain uncontrolled unless the
archived methodology explicitly says otherwise.

Raw paired results: [archive JSON](./{archive_path.name})
"""


def render_markdown(archive_json_path, output_md_path):
    archive_json_path = Path(archive_json_path)
    output_md_path = Path(output_md_path)
    record = json.loads(archive_json_path.read_text(encoding="utf-8"))
    if record.get("format_version") == 3:
        markdown = _comparison_markdown(record, archive_json_path)
    else:
        markdown = _single_markdown(unpack_reports(record), archive_json_path)
    output_md_path.write_text(markdown, encoding="utf-8")
    return output_md_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.source.with_suffix(".md")
    render_markdown(args.source, output)
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
