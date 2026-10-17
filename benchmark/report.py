"""Validate and render complete user-visible query evidence without making requests."""

from copy import deepcopy
import json
import math
from pathlib import Path
import random
import statistics

from benchmark.common import percentile, save_json
from benchmark.e2e import plan
from benchmark.e2e.execution import MAX_CACHE_PREPARATION_PASSES, validate_ledger


def ratio_interval(ratios):
    if len(ratios) < 6:
        return None
    randomizer = random.Random(1729)
    samples = [statistics.median(randomizer.choices(ratios, k=len(ratios))) for _ in range(2000)]
    return [percentile(samples, .025), percentile(samples, .975)]


def experiment_identity(record):
    manifest = record["experiment"]
    return {"plan": record["plan"], "rounds": record["rounds"], "workflow": record["workflow"],
            "harness": manifest["harness"], "harness_dependency_lock": manifest["harness_dependency_lock"],
            "environments": {name: {key: environment[key] for key in
                ("commit", "source_hashes", "dependency_lock")}
                for name, environment in manifest["environments"].items()}}


def collect(source, output):
    paths = sorted(Path(source).rglob("results.json"))
    if not paths:
        raise ValueError("No phase evidence found")
    combined, identity = None, None
    for path in paths:
        record = json.loads(path.read_text())
        shared = experiment_identity(record)
        if identity is not None and shared != identity:
            raise ValueError("Phase evidence mixes workloads, workflow attempts, sources, or dependencies")
        identity = shared
        if combined is None:
            combined = deepcopy(record)
            combined.update(phases=[], records=[], runners={})
        combined["phases"].extend(record["phases"])
        combined["records"].extend(record["records"])
        for phase in record["phases"]:
            combined["runners"][phase["id"]] = record["experiment"]["environments"]
        if record["status"] != "complete":
            combined["status"] = "incomplete"
    combined["phases"].sort(key=lambda phase: plan.phases().index(phase))
    if combined["phases"] != plan.phases():
        raise ValueError("Exactly one copy of all twelve phases is required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    target = output / "results.json"
    save_json(target, combined)
    return target


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate_seed(seed):
    if not isinstance(seed, dict) or seed.get("strategy") != "complete_files" or seed.get("status") != "ready":
        raise ValueError("Missing complete-file cache seed evidence")
    content = {key: value for key, value in seed.items() if key != "sha256"}
    if seed.get("sha256") != plan.checksum(content) or not seed.get("dataset"):
        raise ValueError("Invalid complete-file cache seed identity")
    manifest = seed.get("manifest", {})
    if not manifest or seed.get("manifest_sha256") != plan.checksum(manifest):
        raise ValueError("Invalid cache seed block manifest")
    files = seed.get("files", [])
    if (not files or len({row["file"] for row in files}) != len(files)
            or any(type(row.get("size")) is not int or row["size"] <= 0
                   or row.get("covered_bytes") != row["size"]
                   or not positive(row.get("validated_extents")) for row in files)
            or seed.get("total_bytes") != sum(row["size"] for row in files)):
        raise ValueError("Incomplete cache seed coverage")
    expected = {relative: identity["file_size"]
                for relative, identity in seed["dataset"].get("footer_index", {}).items()
                if relative.startswith("US/") and relative.endswith(".parquet")}
    actual = {row["file"]: row["size"] for row in files}
    if any(actual.get(name) != size for name, size in expected.items()):
        raise ValueError("Cache seed omits a declared dataset file")
    return seed["sha256"]


def validate_preparation(preparation, tasks, phase, seed_sha256):
    if (not isinstance(preparation, dict) or preparation.get("status") != "ready"
            or preparation.get("concurrency") != phase["concurrency"]
            or preparation.get("execution") != ("caller" if phase["kind"] == "latency" else "thread_pool")
            or preparation.get("max_passes") != MAX_CACHE_PREPARATION_PASSES
            or preparation.get("errors") != []
            or preparation.get("seed_sha256") != seed_sha256):
        raise ValueError("Missing or inconsistent cache preparation evidence")
    passes = preparation.get("passes")
    if not isinstance(passes, list) or not 1 <= len(passes) <= MAX_CACHE_PREPARATION_PASSES:
        raise ValueError("Cache preparation exceeded its bound or has no complete pass")
    identifiers = [task["id"] for task in tasks]
    unavailable = sum("not_applicable" in task for task in tasks)
    for index, attempt in enumerate(passes):
        if (attempt.get("number") != index + 1 or attempt.get("task_ids") != identifiers
                or attempt.get("completed_tasks") != len(tasks) or attempt.get("failed_tasks") != 0
                or attempt.get("successful_tasks") != len(tasks) - unavailable
                or attempt.get("not_applicable_tasks") != unavailable):
            raise ValueError("Cache preparation did not replay the complete declared work")
        misses = attempt.get("cache_misses")
        if type(misses) is not int or misses < 0 or (misses == 0) != (index == len(passes) - 1):
            raise ValueError("Cache preparation requires a final zero-request pass")


def validate_measurement(workload, phase, value):
    if value.get("status") != "complete":
        raise ValueError(f"Unsuccessful measurement: {value.get('status')}")
    validate_ledger(workload, value["results"])
    if not value.get("observed_dataset"):
        raise ValueError("Missing observed data identity")
    if value.get("api_coverage") != workload["methods"]:
        raise ValueError("Actual public API coverage differs from the frozen workload")
    seed_sha256 = None
    if phase["state"] == "cached":
        seed = value.get("cache_seed")
        seed_sha256 = validate_seed(seed)
        if seed["dataset"] != value["observed_dataset"]:
            raise ValueError("Measured dataset differs from the prepared cache seed")
    declared = {task["id"]: task for task in plan.tasks(workload)}
    for row in value["results"]:
        task = declared[row["id"]]
        if any(row.get(key) != task[key] for key in ("symbol", "method", "kwargs")):
            raise ValueError("Measured parameters differ from the frozen workload")
        if "not_applicable" in task:
            if row.get("status") != "not_applicable" or row.get("reason") != task["not_applicable"]:
                raise ValueError("Unexpected applicability status")
        elif row.get("status") != "ok" or not row.get("fingerprint") or not positive(row.get("seconds")):
            raise ValueError("Missing result, failed call, or nonpositive timing")
        if phase["kind"] == "latency" and row.get("status") == "ok":
            if not positive(row.get("initialization_seconds")):
                raise ValueError("Missing constructor timing")
            if phase["state"] == "cached":
                validate_preparation(row.get("cache_preparation"), [task], phase, seed_sha256)
    successful = sum(row["status"] == "ok" for row in value["results"])
    if (value.get("completed_tasks") != workload["task_count"]
            or value.get("successful_tasks") != successful
            or value.get("failed_tasks") != 0
            or value.get("not_applicable_tasks") != workload["task_count"] - successful):
        raise ValueError("Completion counters differ from the task ledger")
    settings = value.get("cache_settings", {})
    if (settings.get("disk_limit_bytes") != workload["cache_capacity_bytes"]
            or type(settings.get("native_file_cache")) is not bool
            or not positive(settings.get("memory_limit_bytes"))):
        raise ValueError("Missing or inconsistent cache settings")
    if phase["state"] == "cached" and value.get("cache_misses") != 0:
        raise ValueError("All-hit scenario contains query-data misses")
    if phase["kind"] == "throughput":
        if phase["state"] == "cached":
            validate_preparation(value.get("cache_preparation"), list(declared.values()), phase, seed_sha256)
        if not positive(value.get("wall_seconds")):
            raise ValueError("Invalid batch duration")
        expected = successful / value["wall_seconds"]
        if not math.isclose(value.get("successful_calls_per_second", -1), expected, rel_tol=1e-10):
            raise ValueError("Throughput differs from completed successful work")


def metric(identifier, kind, samples, changed=False):
    variants = {variant: [sample[variant] for sample in samples] for variant in samples[0]} if samples else {}
    row = {"case": identifier, "kind": kind, "pairs": len(samples),
           "medians": {variant: statistics.median(values) for variant, values in variants.items()},
           "classification": "standalone" if "baseline" not in variants else "inconclusive",
           "data_changed": changed}
    if "baseline" in variants:
        ratios = [sample["candidate"] / sample["baseline"] for sample in samples]
        interval = ratio_interval(ratios)
        row.update(reduction_percent=100 * (1 - statistics.median(ratios)), ratio_interval=interval)
        if interval and not changed:
            row["classification"] = "faster" if interval[1] < 1 else "slower" if interval[0] > 1 else "inconclusive"
    return row


def summarize(record):
    errors, rows, groups = [], [], {}
    if record.get("schema_version") != 3:
        return {"valid": False, "errors": ["Unsupported evidence schema"], "cases": []}
    try:
        workload = record["plan"]
        plan.validate_plan(workload)
        phases, rounds = record["phases"], record["rounds"]
        variants = set(record["experiment"]["environments"])
        if variants not in ({"candidate"}, {"baseline", "candidate"}):
            raise ValueError("Unsupported variant set")
        if type(rounds) is not int or rounds < 1 or not phases:
            raise ValueError("Positive rounds and nonempty phases are required")
        if any(phase not in plan.phases() for phase in phases) or len({p["id"] for p in phases}) != len(phases):
            raise ValueError("Unknown or duplicate phase")
        expected = {(phase["id"], number, variant) for phase in phases
                    for number in range(1, rounds + 1) for variant in variants}
        for sample in record["records"]:
            key = (sample["phase"], sample["round"], sample["variant"])
            if key not in expected or key in groups:
                raise ValueError(f"Undeclared or duplicate measurement: {key}")
            groups[key] = sample["measurement"]
        if set(groups) != expected:
            raise ValueError("Missing phase/round/variant measurement")
        for phase in phases:
            try:
                trials, changed, mismatches = [], False, set()
                for number in range(1, rounds + 1):
                    values = {variant: groups[phase["id"], number, variant] for variant in variants}
                    for value in values.values():
                        validate_measurement(workload, phase, value)
                    if len(values) == 2:
                        a, b = values["baseline"], values["candidate"]
                        for setting in ("disk_limit_bytes", "memory_limit_bytes"):
                            if a["cache_settings"][setting] != b["cache_settings"][setting]:
                                raise ValueError("Paired cache capacities differ")
                        same_data = a.get("observed_dataset") == b.get("observed_dataset")
                        if not a.get("observed_dataset") or not b.get("observed_dataset"):
                            raise ValueError("Missing observed data identity")
                        changed |= not same_data
                        fingerprints = [{r["id"]: r.get("fingerprint") for r in value["results"]}
                                        for value in (a, b)]
                        if same_data and fingerprints[0] != fingerprints[1]:
                            different = {key for key in fingerprints[0] if fingerprints[0][key] != fingerprints[1][key]}
                            mismatches.update(different)
                            errors.append(f"Result mismatch: {phase['id']} round {number}: {sorted(different)}")
                    trials.append(values)
                if phase["kind"] == "throughput":
                    samples = [{variant: value["wall_seconds"] for variant, value in trial.items()} for trial in trials]
                    row = metric(phase["id"], "throughput", samples, changed)
                    row["calls_per_second"] = {variant: statistics.median(
                        trial[variant]["successful_calls_per_second"] for trial in trials) for variant in variants}
                    row["p95_seconds"] = {variant: statistics.median(
                        percentile([r["seconds"] for r in trial[variant]["results"] if r["status"] == "ok"], .95)
                        for trial in trials) for variant in variants}
                    if mismatches:
                        row.update(classification="result_mismatch", reduction_percent=None,
                                   ratio_interval=None, mismatched_tasks=sorted(mismatches))
                    rows.append(row)
                else:
                    indexed = [{variant: {r["id"]: r for r in value["results"]}
                                for variant, value in trial.items()} for trial in trials]
                    for task in plan.tasks(workload):
                        if "not_applicable" in task:
                            rows.append({"case": phase["id"] + ":" + task["id"], "kind": "latency",
                                         "classification": "not_applicable", "medians": {}})
                            continue
                        samples = [{variant: trial[variant][task["id"]]["seconds"] for variant in variants}
                                   for trial in indexed]
                        row = metric(phase["id"] + ":" + task["id"], "latency", samples, changed)
                        row["initialization_seconds"] = {variant: statistics.median(
                            trial[variant][task["id"]]["initialization_seconds"] for trial in indexed)
                            for variant in variants}
                        if task["id"] in mismatches:
                            row.update(classification="result_mismatch", reduction_percent=None, ratio_interval=None)
                        rows.append(row)
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                errors.append(f"{phase['id']}: {exc}")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        errors.append(str(exc))
    return {"valid": record.get("status") == "complete" and not errors, "errors": errors, "cases": rows}


def number(value):
    return "n/a" if value is None else f"{value:.4f}"


def render(path, release=None):
    path = Path(path)
    record = json.loads(path.read_text())
    summary = summarize(record)
    lines = ["# End-to-end API performance report", "",
             f"Stage: **final release report** for `{release}`." if release else
             "Stage: **development evidence**; no release publication.", "",
             f"Status: **{'valid' if summary['valid'] else 'incomplete or invalid'}**.", "",
             f"Workload: {len(record['plan']['symbols'])} tickers x {len(record['plan']['methods'])} query operations = "
             f"{record['plan']['task_count']} fixed tasks per phase. Rounds: {record['rounds']}.",
             "Tickers: " + ", ".join(record["plan"]["symbols"]) + ".", "",
             "API latency includes full materialization; constructor, warmup, and hashing are outside it.",
             "Cold latency isolates each task. Cold throughput allows natural sharing within one empty-cache batch.",
             "Cached scenarios warm every applicable task and require zero query-data cache misses.",
             "Complete remote files are prepared and coverage-validated outside timing; one API warmup uses the measurement concurrency.",
             "Each isolated cache links immutable seed blocks and copies mutable metadata; this is not ordinary second-call latency.",
             "Preparation is outside timing. Any subsequent measured miss invalidates the scenario; measured calls are never resampled.",
             "Every throughput concurrency executes the same complete Cartesian workload once.", "",
             "## Provenance", "", "| Variant | Commit | DuckDB | Python |", "| --- | --- | --- | --- |"]
    for name, env in record["experiment"]["environments"].items():
        info = env["environment"]
        lines.append(f"| {name} | `{env['commit']}` | {info['dependencies']['duckdb']} | {info['python']} |")
    lines += ["", "Baseline and candidate run sequentially on the same runner for each phase.",
              "Different phases can use different runners. Compare paired ratios, not cross-job absolute times.",
              "Cache capacities are generous and equal within pairs; this is an all-local-hit capacity assumption.",
              "Daily remote changes are recorded; changed-data pairs remain inconclusive.", "",
              "Intervals need at least six pairs and are per-case bootstrap intervals without multiplicity correction.",
              "Fewer rounds show exploratory medians, without a faster/slower verdict.", "",
              "## Throughput", "", "| Scenario | Baseline batch (s) | Candidate batch (s) | Baseline calls/s | Candidate calls/s | Baseline P95 (s) | Candidate P95 (s) | Reduction | Verdict |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in summary["cases"]:
        if row["kind"] != "throughput":
            continue
        medians, rates, tails = row["medians"], row["calls_per_second"], row["p95_seconds"]
        lines.append(f"| {row['case']} | {number(medians.get('baseline'))} | {number(medians.get('candidate'))} | "
                     f"{number(rates.get('baseline'))} | {number(rates.get('candidate'))} | "
                     f"{number(tails.get('baseline'))} | {number(tails.get('candidate'))} | "
                     f"{number(row.get('reduction_percent'))}% | {row['classification']} |")
    lines += ["", "## Individual query latency", "",
              "| Scenario / ticker / method | Baseline API (s) | Candidate API (s) | Baseline init (s) | Candidate init (s) | Reduction | Verdict |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in summary["cases"]:
        if row["kind"] != "latency":
            continue
        medians, init = row["medians"], row.get("initialization_seconds", {})
        lines.append(f"| `{row['case']}` | {number(medians.get('baseline'))} | {number(medians.get('candidate'))} | "
                     f"{number(init.get('baseline'))} | {number(init.get('candidate'))} | "
                     f"{number(row.get('reduction_percent'))}% | {row['classification']} |")
    lines += ["", "## Phase coverage", "",
              "| Phase | Round | Variant | Status | Completed | Successful | Failed | Not applicable | Preparation passes |",
              "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    failures = []
    for sample in record["records"]:
        value = sample["measurement"]
        preparation = value.get("cache_preparation")
        passes = (len(preparation["passes"]) if preparation else
                  "per query" if sample["phase"] == "latency.cached" else "n/a")
        lines.append(f"| {sample['phase']} | {sample['round']} | {sample['variant']} | {value.get('status')} | "
                     f"{value.get('completed_tasks', 0)} | {value.get('successful_tasks', 0)} | "
                     f"{value.get('failed_tasks', 0)} | {value.get('not_applicable_tasks', 0)} | {passes} |")
        for row in value.get("results", []) + value.get("warmup_errors", []):
            if row.get("status") == "error":
                failures.append(f"- `{sample['phase']}` / round {sample['round']} / `{sample['variant']}` / "
                                f"`{row.get('symbol')}` / `{row.get('method')}`: `{row.get('error_type')}`.")
    lines += ["", "## Query failures", ""] + (failures or ["No query failures recorded."])
    lines += ["", "## Validation", ""] + [f"- {error}" for error in summary["errors"]]
    lines += ["", "Skipped source bodies remain not applicable and never count as successful calls.",
              "Empty successful results are retained. Errors and missing tasks invalidate acceptance.",
              "Full ledgers, parameters, cache settings, initialization, environment, and fingerprints are in",
              "[results.json](results.json). No protocol or bandwidth benchmark is part of this report.", ""]
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    save_json(path.with_name("results_summary.json"), summary)
    return summary
