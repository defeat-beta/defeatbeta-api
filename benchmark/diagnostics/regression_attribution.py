"""Separate engine and project changes with three isolated diagnostic arms.

The engine-only arm intentionally runs baseline source on the candidate engine.
It is not a supported dependency combination or a replacement release baseline.
"""

import argparse
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from itertools import permutations
import json
import os
from pathlib import Path
import shutil
import tempfile

from benchmark.benchmark import execute, prepare
from benchmark.common import save_json
from benchmark.fixture import generate, verify
from benchmark.report import fingerprints, render
from benchmark.server import serve_fixture
from benchmark.suite import make_suite


ARMS = ("baseline", "engine_only", "candidate")
ORDERS = tuple(permutations(ARMS))
COMPARISONS = {"engine": ("baseline", "engine_only"),
               "project": ("engine_only", "candidate"), "total": ("baseline", "candidate")}
CASE_IDS = {"info.first_use", "info.metadata_ready", "officers.memory_warm",
            "calendar.memory_warm", "splits.memory_warm", "dividends.memory_warm",
            *(f"mixed.stream.{count}" for count in (1, 16, 64, 128))}


def make_arms(manifest):
    environments = manifest["environments"]
    baseline, candidate = environments["baseline"], environments["candidate"]
    def other_dependencies(environment):
        return sorted(line for line in environment["dependency_lock"].splitlines()
                      if not line.lower().startswith("duckdb=="))
    if other_dependencies(baseline) != other_dependencies(candidate):
        raise ValueError("Engine attribution requires identical non-DuckDB dependencies")
    engine = deepcopy(baseline)
    for name in ("python", "environment", "dependency_lock"):
        engine[name] = deepcopy(candidate[name])
    engine["diagnostic_override"] = "Baseline source executed by the candidate interpreter and dependencies"
    return {"baseline": deepcopy(baseline), "engine_only": engine, "candidate": deepcopy(candidate)}


def make_plan():
    plan = make_suite("release", cache_policy="project-only")
    plan["name"] = "regression-attribution"
    plan["cases"] = [{**case, "diagnostics": {"memory": True}}
                     for case in plan["cases"] if case["id"] in CASE_IDS]
    plan["methods"] = sorted({task["method"] for case in plan["cases"] for task in case["tasks"]})
    plan.pop("sha256")
    plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def arm_order(round_index, case_index):
    return ORDERS[(round_index + case_index) % len(ORDERS)]


def comparison_record(record, name):
    first, second = COMPARISONS[name]
    variants = {first: "baseline", second: "candidate"}
    value = {key: deepcopy(record[key]) for key in
             ("schema_version", "stage", "status", "mode", "rounds", "network", "suite", "workflow")}
    value["resolved_suite_sha256"] = hashlib.sha256(json.dumps(value["suite"], sort_keys=True).encode()).hexdigest()
    value["experiment"] = {**deepcopy(record["experiment"]), "environments": {
        variants[arm]: record["arms"][arm] for arm in (first, second)}}
    value["records"] = [{**sample, "variant": variants[sample["variant"]]}
                        for sample in record["records"] if sample["variant"] in variants]
    return value


def validate_profile(measurement, reference):
    if measurement.get("status") != "ok":
        raise ValueError("Profile worker failed")
    if measurement["cache_total_delta"]["range_requests"]:
        raise ValueError("A fully cached profile unexpectedly used the network")
    if not measurement.get("diagnostics", {}).get("instrumented"):
        raise ValueError("Profile must be marked as instrumented")
    same_data = (measurement["dataset_version"] == reference["dataset_version"]
                 and measurement["file_metadata"] == reference["file_metadata"])
    if same_data and fingerprints(measurement) != fingerprints(reference):
        raise ValueError("Profile result differs from the uninstrumented query")
    return "matching result" if same_data else "data changed; result comparison unavailable"


def run(args):
    args.baseline_lock = args.candidate_lock = None
    experiment = prepare(args)
    manifest = json.loads((experiment / "experiment.json").read_text())
    arms = make_arms(manifest)
    record = {"schema_version": 1, "stage": "development", "status": "running",
              "created_at": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
              "network": args.network_label, "rounds": args.rounds, "suite": make_plan(),
              "experiment": manifest, "arms": arms, "records": [], "profiles": [],
              "workflow": {key: os.environ.get(env) for key, env in (
                  ("repository", "GITHUB_REPOSITORY"), ("run_id", "GITHUB_RUN_ID"),
                  ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("sha", "GITHUB_SHA"))},
              "methodology": {
                  "arms": "Declared baseline; baseline source on candidate engine; declared candidate",
                  "order": "All six arm permutations across six rounds, offset by case",
                  "timing": "Existing worker and workload; extra memory sampling outside query timing",
                  "profiles": "Separate warmed workers; cProfile timings excluded from comparisons",
                  "memory": "RSS milestones plus DuckDB buffer accounting; not a peak or leak measurement",
                  "scope": "Diagnostic subset; cannot be promoted as a complete release report"}}
    target = experiment / "attribution.json"
    save_json(target, record)
    with tempfile.TemporaryDirectory(prefix="defeatbeta-attribution-") as temporary:
        temporary = Path(temporary)
        if args.mode == "controlled":
            generate(temporary / "fixture")
            record["fixture"] = verify(temporary / "fixture")
            context = serve_fixture(temporary / "fixture", temporary)
        else:
            context = nullcontext(None)
        with context as server:
            for number in range(args.rounds):
                for index, case in enumerate(record["suite"]["cases"]):
                    for arm in arm_order(number, index):
                        directory = temporary / f"cache-{number}-{index}-{arm}"
                        directory.mkdir()
                        print(f"round={number + 1} case={case['id']} arm={arm}", flush=True)
                        value = execute(experiment, arms[arm], case, directory, args.timeout, server)
                        record["records"].append({"case": case["id"], "round": number + 1,
                                                  "variant": arm, "measurement": value})
                        save_json(target, record)
                        shutil.rmtree(directory)
                        print(f"  {value['status']} seconds={value.get('wall_seconds')}", flush=True)
            if args.profile_repeats:
                for index, case in enumerate(record["suite"]["cases"]):
                    if case["state"] != "memory_warm":
                        continue
                    profiled = {**case, "diagnostics": {"memory": True, "profile_repeats": args.profile_repeats}}
                    for arm in arm_order(0, index):
                        directory = temporary / f"profile-{index}-{arm}"
                        directory.mkdir()
                        value = execute(experiment, arms[arm], profiled, directory, args.timeout, server)
                        reference = next(item["measurement"] for item in record["records"]
                                         if item["case"] == case["id"] and item["variant"] == arm)
                        try:
                            validation = validate_profile(value, reference)
                        except (ValueError, KeyError) as exc:
                            validation = type(exc).__name__ + ": " + str(exc)
                            record["profile_failed"] = True
                        record["profiles"].append({"case": case["id"], "variant": arm,
                                                   "measurement": value, "validation": validation})
                        save_json(target, record)
                        shutil.rmtree(directory)
    record["status"] = "complete"
    save_json(target, record)
    valid = not record.get("profile_failed", False)
    for name in COMPARISONS:
        path = experiment / name / "results.json"
        path.parent.mkdir(exist_ok=True)
        save_json(path, comparison_record(record, name))
        valid = render(path)["valid"] and valid
    return 0 if valid else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="release-0.0.62")
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("controlled", "live"), default="controlled")
    parser.add_argument("--network-label", default="Unspecified diagnostic environment")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--profile-repeats", type=int, default=100)
    args = parser.parse_args()
    if args.rounds < 1 or args.profile_repeats < 0 or not 0 < args.timeout < float("inf"):
        parser.error("Rounds and timeout must be positive; profile repetitions must be nonnegative")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
