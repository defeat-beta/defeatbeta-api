"""Compare cold and restarted disk-cache batches on one runner using isolated versions."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from benchmark.benchmark import execute, paired_order, prepare, verify_harness
from benchmark.common import ROOT, save_json
from benchmark.e2e.plan import tasks, validate_plan


CONCURRENCIES = (1, 4, 16, 64)


def case_order(round_index):
    order = CONCURRENCIES if round_index % 2 == 0 else tuple(reversed(CONCURRENCIES))
    return [(n, variant) for n in order for variant in paired_order(round_index, CONCURRENCIES.index(n))]


def mismatches(records):
    """Do not confuse nonidentical outputs with a valid performance comparison."""
    references, changed = {}, set()
    for record in records:
        for row in record["measurement"].get("results", []):
            if row["status"] != "ok":
                continue
            value = row.get("fingerprint")
            if row["id"] in references and references[row["id"]] != value:
                changed.add(row["id"])
            references[row["id"]] = value
    return sorted(changed)


def _cache_label(record):
    return "Disk reuse (round 1)" if record.get("cache_state") == "disk_reuse" else "Cold (empty files)"


def _seconds(value):
    return f"{value:.3f}" if value is not None else "unavailable"


def _by_case(records):
    """Index measured batches by (round, version, workers)."""
    return {(r["round"], r["variant"], r["concurrency"]): r["measurement"] for r in records}


def _concurrencies(report):
    records = report["records"]
    return report.get("concurrencies", sorted({r["concurrency"] for r in records}) or CONCURRENCIES)


def _round_lines(report, number):
    cases = _by_case(report["records"])
    title = ("Round 1: cold start (empty disk cache)" if number == 1
             else "Round 2: reuse the round 1 disk cache in a new process")
    lines = [f"## {title}", "",
             "| Workers | Baseline seconds | Candidate seconds | Speedup | Baseline calls/s | "
             "Candidate calls/s | Failed calls (baseline / candidate) | Status (baseline / candidate) |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for workers in _concurrencies(report):
        old = cases.get((number, "baseline", workers), {})
        new = cases.get((number, "candidate", workers), {})
        complete = old.get("status") == new.get("status") == "complete"
        speedup = (f"{old['wall_seconds'] / new['wall_seconds']:.2f}x"
                   if complete and old.get("wall_seconds") and new.get("wall_seconds") else "unavailable")
        lines.append(
            f"| {workers} | {_seconds(old.get('wall_seconds'))} | {_seconds(new.get('wall_seconds'))} | "
            f"{speedup} | {_seconds(old.get('successful_calls_per_second'))} | "
            f"{_seconds(new.get('successful_calls_per_second'))} | "
            f"{old.get('failed_tasks', 'unavailable')} / {new.get('failed_tasks', 'unavailable')} | "
            f"{old.get('status', 'not run')} / {new.get('status', 'not run')} |")
    lines += ["", f"### Round {number} downloads", "",
              "| Version | Workers | cache_hits | cache_misses | downloaded_bytes | range_requests | range_seconds |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for variant in ("baseline", "candidate"):
        for workers in _concurrencies(report):
            if (number, variant, workers) not in cases:
                continue
            metrics = cases[number, variant, workers].get("requests", {}).get("metrics", {})
            values = [str(metrics.get(key, "unavailable")) for key in (
                "cache_hits", "cache_misses", "downloaded_bytes", "range_requests")]
            values.append(_seconds(metrics.get("range_seconds")))
            lines.append(f"| {variant} | {workers} | {' | '.join(values)} |")
    return lines + [""]


def _output_lines(report):
    changed = report.get("mismatched_task_ids", [])
    lines = ["## Output equivalence", "",
             "Fingerprints hash column names and every normalized row value, retaining duplicate rows "
             "but ignoring row order. Numeric differences, including small floating-point differences, "
             "are not rounded away. Fingerprints do not identify which individual values changed.",
             f"Tasks with changed output fingerprints across batches: {len(changed)}.", ""]
    if changed:
        # Group identical results so each distinct digest appears once per version.
        groups = defaultdict(list)
        for record in report["records"]:
            for row in record["measurement"].get("results", []):
                if row["id"] not in changed or row["status"] != "ok":
                    continue
                value = row.get("fingerprint") or {}
                key = (row["id"], record["variant"], value.get("sha256", "unavailable"))
                groups[key].append((record["round"], record["concurrency"], row, value))
        order = {"baseline": 0, "candidate": 1}
        lines += ["Each row is one distinct result of a changed task, with the batches that produced it. "
                  "Changes within the baseline must not be attributed only to the candidate.", "",
                  "| Ticker | Operation | Version | Rows | SHA-256 | Batches (round/workers) |",
                  "| --- | --- | --- | ---: | --- | --- |"]
        first_batch = {key: min(item[:2] for item in items) for key, items in groups.items()}
        for task_id, variant, digest in sorted(groups, key=lambda k: (changed.index(k[0]), order.get(k[1], 2),
                                                                       first_batch[k])):
            batches = sorted(groups[task_id, variant, digest], key=lambda item: item[:2])
            _, _, row, value = batches[0]
            where = ", ".join(f"{number}/{workers}" for number, workers, _, _ in batches)
            lines.append(f"| {row['symbol']} | {row['method']} | {variant} | "
                         f"{value.get('rows', 'unavailable')} | `{digest}` | {where} |")
    return lines + [""]


def _method_lines(report):
    workload = report["plan"]
    validate_plan(workload)
    concurrencies = _concurrencies(report)
    batches = report["rounds"] * len(concurrencies) * 2
    lines = ["## Method", "",
             f"{len(workload['symbols'])} tickers x {len(workload['methods'])} query operations = "
             f"{workload['task_count']} tasks per batch. Tickers: {', '.join(workload['symbols'])}.",
             f"Workers: {', '.join(map(str, concurrencies))}. Every worker count runs the same workload once; "
             "it does not multiply the task count.",
             f"Two versions x {len(concurrencies)} worker counts x {report['rounds']} rounds = "
             f"{batches} planned batches. Recorded batches: {len(report['records'])}. "
             f"Frozen workload SHA-256: `{workload['sha256']}`.", "",
             "- All batches run sequentially on one runner. Each version has isolated source and dependencies, "
             "and every batch runs in a separate Python process.",
             "- Round 1 starts from an empty disk cache. Round 2 reuses the round 1 cache files of the same "
             "version and worker count; memory caches and connections start fresh, and a few downloads may remain.",
             "- Do not average the two rounds: they measure different disk-cache states.",
             "- Batch seconds exclude Ticker initialization, output fingerprinting and the final "
             "pending-download drain. No workload replay or connection warmup runs before timing.",
             "- Download counters are the cachefs counters of Ticker.download_data_performance(), as query-phase "
             "deltas. Native DuckDB cache hits can bypass cachefs; range_seconds sums overlapping requests.",
             "- Both versions use the same cache budgets rather than their defaults.", "",
             "Excluded operations:", ""]
    lines += [f"- `{name}`: {reason}." for name, reason in workload["exclusions"].items()]
    lines += ["", "<details>", "<summary>All query operations and frozen parameters</summary>", "",
              "| Operation | Call | Frozen parameters by ticker |", "| --- | --- | --- |"]
    parameters = defaultdict(lambda: defaultdict(list))
    for task in tasks(workload):
        value = ("not applicable: " + task["not_applicable"] if "not_applicable" in task
                 else json.dumps(task["kwargs"], sort_keys=True, ensure_ascii=True))
        parameters[task["method"]][value].append(task["symbol"])
    for name, spec in workload["methods"].items():
        descriptions = [f"{', '.join(symbols)}: `{value}`" for value, symbols in parameters[name].items()]
        cells = "<br>".join(descriptions).replace("|", "&#124;")
        lines.append(f"| `{name}` | `{spec['call']}` | {cells} |")
    lines += ["", "</details>", "", "<details>", "<summary>Execution order</summary>", "",
              "Versions alternate between worker counts to spread runner drift across both versions.", "",
              "| Order | Round | Version | Workers | Cache state | Cache source | Initialization seconds | Status |",
              "| ---: | ---: | --- | ---: | --- | --- | ---: | --- |"]
    for index, record in enumerate(report["records"], 1):
        m = record["measurement"]
        lines.append(f"| {index} | {record['round']} | {record['variant']} | {record['concurrency']} | "
                     f"{_cache_label(record)} | {record.get('cache_source_case') or 'none'} | "
                     f"{_seconds(m.get('initialization_seconds'))} | {m.get('status', 'unavailable')} |")
    return lines + ["", "</details>", ""]


def render(report):
    lines = ["# End-to-end concurrency comparison", "", f"Status: {report['status']}", "",
             "Development measurement of baseline versus candidate; not a final release report.", ""]
    for number in range(1, report["rounds"] + 1):
        lines += _round_lines(report, number)
    lines += _output_lines(report)
    lines += _method_lines(report)
    return "\n".join(lines) + "\n"


def run(args):
    if args.rounds != 2:
        raise ValueError("The cold and disk-reuse comparison requires exactly two rounds")
    experiment = prepare(args)
    manifest = json.loads((experiment / "experiment.json").read_text(encoding="utf-8"))
    verify_harness(ROOT / "benchmark", experiment / "harness" / "benchmark", manifest["harness"])
    if set(manifest["environments"]) != {"baseline", "candidate"}:
        raise ValueError("Both isolated versions are required")
    discovery = execute(experiment, manifest["environments"]["candidate"], {"action": "discover"},
                        experiment / "discovery", args.timeout)
    save_json(experiment / "discovery.json", discovery)
    shutil.rmtree(experiment / "discovery" / "cache", ignore_errors=True)
    if discovery["status"] != "complete":
        raise RuntimeError("Workload discovery failed; inspect discovery.json")
    workload = discovery["plan"]
    validate_plan(workload)
    save_json(experiment / "plan.json", workload)
    report = {"schema_version": 2, "status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "experiment": manifest, "plan": workload, "rounds": args.rounds,
              "concurrencies": list(CONCURRENCIES), "cache_states": {"1": "cold", "2": "disk_reuse"},
              "records": []}

    def save():
        report["mismatched_task_ids"] = mismatches(report["records"])
        save_json(experiment / "results.json", report)
        (experiment / "results.md").write_text(render(report), encoding="utf-8")

    save()
    try:
        for number in range(args.rounds):
            for concurrency, variant in case_order(number):
                state = "cold" if number == 0 else "disk_reuse"
                source_case = f"case-1-{concurrency}-{variant}" if number else None
                report["active_case"] = {"round": number + 1, "variant": variant, "concurrency": concurrency,
                                         "cache_state": state, "cache_source_round": 1 if number else None,
                                         "cache_source_case": source_case}
                save()
                print(f"Starting round={number + 1} variant={variant} concurrency={concurrency}", flush=True)
                phase = {"id": f"throughput.{state}.{concurrency}", "kind": "throughput",
                         "state": state, "concurrency": concurrency}
                directory = experiment / f"case-{number + 1}-{concurrency}-{variant}"
                request = {"action": "measure", "phase": phase, "plan": workload}
                if source_case:
                    request["reuse_cache_directory"] = str(experiment / source_case / "cache")
                value = execute(experiment, manifest["environments"][variant],
                                request, directory, args.timeout)
                report["records"].append({**report["active_case"], "measurement": value})
                save()
                if value.get("status") != "complete":
                    raise RuntimeError("Incomplete batch; inspect saved evidence")
                if any(key in value for key in ("diagnostics", "process_diagnostics")):
                    raise RuntimeError("Unexpected instrumentation in plain comparison")
                if value.get("observed_dataset") != workload["dataset"]:
                    raise ValueError("Dataset identity changed during the comparison")
                print(f"Completed round={number + 1} variant={variant} concurrency={concurrency} "
                      f"seconds={value['wall_seconds']:.3f}", flush=True)
        report["status"] = "complete"
        report.pop("active_case", None)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="release-0.0.62")
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=(2,), default=2)
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()
    if args.rounds < 1 or not 0 < args.timeout < float("inf"):
        parser.error("Rounds and timeout must be positive and finite")
    run(args)


if __name__ == "__main__":
    main()
