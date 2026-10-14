"""Render paired performance evidence without rerunning or selecting samples."""

import hashlib
import json
import math
from pathlib import Path
import random
import statistics

from benchmark.common import percentile, save_json


def ratio_interval(ratios):
    if len(ratios) < 6:
        return None
    randomizer = random.Random(1729)
    samples = [statistics.median(randomizer.choices(ratios, k=len(ratios))) for _ in range(2000)]
    return [percentile(samples, .025), percentile(samples, .975)]


def primary(case, measurement):
    if case["kind"] == "single":
        return measurement["first_result_seconds"] if case["state"] in ("first_use", "disk_warm") else measurement["wall_seconds"]
    return measurement["wall_seconds"]


def fingerprints(measurement):
    return [(item["task"], item.get("result")) for item in measurement.get("results", [])]


def valid_engine_cache(measurement, policy):
    observed = measurement.get("engine_cache", {})
    initial = observed.get("initial_external_file_cache")
    effective = observed.get("effective_external_file_cache")
    return (policy in ("default", "project-only") and observed.get("policy") == policy
            and type(initial) is bool and type(effective) is bool
            and (effective == initial if policy == "default" else effective is False))


def summarize(record):
    groups = {}
    errors = []
    if record.get("schema_version") != 1:
        return {"valid": False, "errors": ["Unsupported evidence schema"], "cases": []}
    cases = record["suite"]["cases"]
    rounds = record["rounds"]
    if not cases or type(rounds) is not int or rounds < 1:
        return {"valid": False, "errors": ["A nonempty suite and positive integer rounds are required"], "cases": []}
    identifiers = [case["id"] for case in cases]
    if len(identifiers) != len(set(identifiers)):
        errors.append("Duplicate case identifiers")
    expected = {(case["id"], number, variant) for case in cases
                for number in range(1, rounds + 1) for variant in ("baseline", "candidate")}
    for sample in record["records"]:
        key = (sample["case"], sample["round"], sample["variant"])
        if key not in expected:
            errors.append(f"Undeclared measurement: {key}")
        if key in groups:
            errors.append(f"Duplicate measurement: {key}")
        groups[key] = sample["measurement"]
    rows = []
    for case in record["suite"]["cases"]:
        base, candidate, ratios, notes = [], [], [], []
        failed = 0
        for round_number in range(1, record["rounds"] + 1):
            a = groups.get((case["id"], round_number, "baseline"))
            b = groups.get((case["id"], round_number, "candidate"))
            if a is None or b is None:
                failed += 1
                errors.append(f"Missing pair: {case['id']} round {round_number}")
                continue
            if a.get("status") != "ok" or b.get("status") != "ok":
                failed += 1
                errors.append(f"Failed pair: {case['id']} round {round_number}")
                continue
            if record["suite"]["version"] >= 2:
                policy = record["suite"].get("cache_policy")
                if (case.get("cache_policy") != policy
                        or any(not valid_engine_cache(item, policy) for item in (a, b))):
                    failed += 1
                    errors.append(f"Cache policy differs from observed settings: {case['id']} round {round_number}")
                    continue
            if any(not item.get("results") or any(not result.get("result") for result in item["results"])
                   for item in (a, b)):
                failed += 1
                errors.append(f"Missing result fingerprint: {case['id']} round {round_number}")
                continue
            if "tasks" in case and any([item["task"] for item in value["results"]] != case["tasks"] for value in (a, b)):
                failed += 1
                errors.append(f"Measured tasks differ from the manifest: {case['id']} round {round_number}")
                continue
            same_data = a.get("dataset_version") == b.get("dataset_version") and a.get("file_metadata") == b.get("file_metadata")
            if record["mode"] == "controlled" or same_data:
                if fingerprints(a) != fingerprints(b):
                    errors.append(f"Result mismatch: {case['id']} round {round_number}")
                    failed += 1
                    continue
            elif "Remote data changed; timing retained, result equality not required" not in notes:
                notes.append("Remote data changed; timing retained, result equality not required")
            av, bv = primary(case, a), primary(case, b)
            if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in (av, bv)):
                errors.append(f"Nonpositive or nonfinite timing: {case['id']}")
                failed += 1
                continue
            base.append(av)
            candidate.append(bv)
            ratios.append(bv / av)
        interval = ratio_interval(ratios) if failed == 0 else None
        classification = "invalid" if failed else "inconclusive"
        if interval is not None and not notes:
            classification = "faster in this run" if interval[1] < 1 else "slower in this run" if interval[0] > 1 else "inconclusive"
        rows.append({"case": case["id"], "pairs": len(ratios), "failed_pairs": failed,
                     "baseline_median_seconds": statistics.median(base) if base else None,
                     "candidate_median_seconds": statistics.median(candidate) if candidate else None,
                     "paired_latency_reduction_percent": 100 * (1 - statistics.median(ratios)) if ratios else None,
                     "candidate_over_baseline_ratio_interval": interval,
                     "classification": classification, "notes": notes,
                     "baseline_trials": base, "candidate_trials": candidate})
    return {"valid": record["status"] == "complete" and not errors, "errors": errors, "cases": rows}


def format_value(value, digits=4):
    return "n/a" if value is None else f"{value:.{digits}f}"


def render(path, release=None):
    path = Path(path)
    record = json.loads(path.read_text())
    summary = summarize(record)
    environments = record["experiment"]["environments"]
    stage = (f"Stage: **final release report** for `{release}`. The original raw evidence is unchanged."
             if release else "Stage: **development evidence**. This run does not publish a final release report.")
    lines = ["# Paired API performance report", "", stage, "",
             f"Status: **{'valid comparison' if summary['valid'] else 'incomplete or invalid comparison'}**.", "",
             f"Mode: `{record['mode']}`. Network: {record['network']}. Rounds: {record['rounds']}.", "",
             "The baseline and candidate ran sequentially on one host. Results describe this experiment.",
             "Daily remote updates are accepted and recorded; cross-date absolute times are not a fixed baseline.", "",
             "## Provenance", "", "| Variant | Source commit | DuckDB | Python |", "| --- | --- | --- | --- |"]
    for name, env in environments.items():
        info = env["environment"]
        lines.append(f"| {name} | `{env['commit']}` | {info['dependencies']['duckdb']} | {info['python']} |")
    lines += ["", f"Cache policy: `{record['suite'].get('cache_policy', 'legacy: not recorded per sample')}`.",
              "Default policy preserves each product's native file-cache setting. Project-only policy disables it for diagnostics.",
              "Project-only results cannot replace default-behavior release acceptance.", "",
              "| Variant | Native file cache before preparation | Native file cache during queries |",
              "| --- | --- | --- |"]
    for name in environments:
        observations = [sample["measurement"].get("engine_cache", {}) for sample in record["records"]
                        if sample["variant"] == name]
        settings = [", ".join(sorted({str(item.get(key, "not recorded")).lower() for item in observations}))
                    for key in ("initial_external_file_cache", "effective_external_file_cache")]
        lines.append(f"| {name} | {settings[0] or 'not recorded'} | {settings[1] or 'not recorded'} |")
    info = environments["candidate"]["environment"]
    lines += ["", f"Platform: {info['platform']}; logical CPUs: {info['cpu_count']}; RAM: {info['ram_bytes']} bytes.",
              f"Suite: `{record['suite']['name']}` v{record['suite']['version']}; resolved identity: `{record.get('resolved_suite_sha256', 'unresolved')}`.",
              "Dependency locks, source hashes, route, default policies, data versions, and raw attempts are embedded in the JSON.", "",
              "## Timing comparison", "",
              "For first use and disk-warm restart, the primary metric includes the constructor and API call.",
              "Other single cases measure the complete API call; concurrent cases measure complete batch wall time.",
              "Positive reduction means faster: `100 * (1 - median(candidate / baseline per pair))`.",
              "Intervals resample paired rounds; individual requests within a batch are not independent replicates.",
              "With fewer than six pairs, results remain exploratory. No universal regression threshold is applied.", "",
              "| Case | Pairs | Baseline median (s) | Candidate median (s) | Reduction (%) | Ratio interval (95%) | Assessment |",
              "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for row in summary["cases"]:
        interval = row["candidate_over_baseline_ratio_interval"]
        bounds = "exploratory" if interval is None else " - ".join(format_value(value, 3) for value in interval)
        lines.append(f"| {row['case']} | {row['pairs']} | {format_value(row['baseline_median_seconds'])} | "
                     f"{format_value(row['candidate_median_seconds'])} | {format_value(row['paired_latency_reduction_percent'], 1)} | {bounds} | {row['classification']} |")
    lines += ["", "## Resource and concurrency measurements", "",
              "Values below are medians of successful attempts. Failures remain in the raw record and invalidate the case.",
              "Application bytes include prefetch drain and are not wire bandwidth. Stream batches begin with cold query data",
              "and can develop cache hits while executing the fixed plan. P95 is an empirical within-batch observation.", "",
              "| Case | Variant | Calls/s | API P95 (s) | CPU (s) | RSS at end (MiB) | Downloaded bytes | Range GETs | Pool wait (s) |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in record["suite"]["cases"]:
        for variant in ("baseline", "candidate"):
            items = [sample["measurement"] for sample in record["records"]
                     if sample["case"] == case["id"] and sample["variant"] == variant
                     and sample["measurement"].get("status") == "ok"]
            if not items:
                continue
            def median(extract):
                values = [extract(item) for item in items]
                return statistics.median(values) if all(value is not None for value in values) else None
            values = [median(lambda item: item["completed_calls_per_second"]),
                      median(lambda item: item["latency"]["p95_seconds"]),
                      median(lambda item: item["cpu_seconds"]),
                      median(lambda item: item["rss_bytes_at_query_end"] / 1024**2),
                      median(lambda item: item["cache_total_delta"]["downloaded_bytes"]),
                      median(lambda item: item["cache_total_delta"]["range_requests"]),
                      median(lambda item: item["pool_after"]["pool_wait_seconds"] - item["pool_before"]["pool_wait_seconds"]
                             if item.get("pool_after") is not None else None)]
            lines.append(f"| {case['id']} | {variant} | " + " | ".join(format_value(value) for value in values) + " |")
    lines += ["", "## Validation and limitations", ""]
    lines += [f"- {error}" for error in summary["errors"]] or ["- All declared pairs completed and applicable result checks passed."]
    for row in summary["cases"]:
        for note in row["notes"]:
            lines.append(f"- {row['case']}: {note}.")
    lines += ["- A successful comparison is evidence, not automatic permission to publish a package.",
              "- The controlled server uses unshaped loopback TLS; server CPU, RSS, protocol and byte counters are recorded separately.",
              "- The controlled fixture is synthetic; real data and public-network behavior are evaluated separately.",
              "- The benchmark does not flush DNS, OS pages, proxy caches, or remote CDN caches.",
              "- Individual API coverage and exclusions are recorded in the resolved experiment.", "",
              "## Evidence and reproduction", "",
              f"Raw evidence: [{path.name}]({path.name}). SHA256: `{hashlib.sha256(path.read_bytes()).hexdigest()}`.", "",
              "```sh", f"python -m benchmark report {path.name}", "```", "",
              "To repeat measurements, use the recorded commits, dependency locks, suite, and order. Public-network runs use current data.",
              "Actions artifacts have finite retention; promote selected JSON and Markdown files together to a durable archive.", ""]
    content = "\n".join(lines)
    if any("\u4e00" <= char <= "\u9fff" for char in content):
        raise ValueError("Report text must be English")
    path.with_suffix(".md").write_text(content, encoding="utf-8")
    save_json(path.with_name(path.stem + "_summary.json"), summary)
    return summary
