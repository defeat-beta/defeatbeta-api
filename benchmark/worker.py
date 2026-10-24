"""Run the frozen end-to-end contract inside one isolated product interpreter."""

import json
from pathlib import Path
import sys
import time

from benchmark.support.adapter import dataset_endpoint
from benchmark.common import environment_info, redact_secrets, source_hashes
from benchmark.e2e.backend import ProductBackend, discover
from benchmark.e2e.execution import measure_throughput
from benchmark.e2e.plan import query_methods
from benchmark.e2e.probe import exception_details


MARKER = "BENCHMARK_RESULT="


def run(payload):
    import defeatbeta_api
    from defeatbeta_api.data.ticker import Ticker

    source = Path(payload["source"]).resolve()
    if Path(defeatbeta_api.__file__).resolve().parent.parent != source:
        raise RuntimeError("Product import escaped the selected source snapshot")
    if source_hashes(source) != payload["source_hashes"]:
        raise RuntimeError("Product sources changed after environment preparation")
    if environment_info()["dependencies"] != payload["dependencies"]:
        raise RuntimeError("Measured dependencies differ from the prepared environment")
    workload = payload.get("plan")
    phase = payload.get("phase", {})
    directory = payload["cache_directory"]
    if phase.get("state") == "disk_reuse":
        if phase.get("kind") != "throughput":
            raise ValueError("Disk reuse requires a throughput batch")
        directory = payload["reuse_cache_directory"]
    backend = ProductBackend(directory, workload)
    with dataset_endpoint(payload.get("endpoint")):
        try:
            if payload["action"] == "discover":
                return {"status": "complete", "plan": discover(backend)}
            available = query_methods(Ticker)
            missing = set(workload["methods"]) - set(available)
            if missing:
                raise ValueError(f"Product does not implement frozen query operations: {sorted(missing)}")
            phase = payload["phase"]
            deadline = time.monotonic() + payload.get("time_budget_seconds", 18000)
            def stop():
                return time.monotonic() >= deadline
            if phase.get("kind") != "throughput":
                raise ValueError("Only throughput batches are supported")
            result = measure_throughput(workload, backend, phase["state"], phase["concurrency"], stop=stop)
            result["cache_settings"] = backend.settings()
            result["api_coverage"] = available
            result["observed_dataset"] = backend.dataset()
            return result
        finally:
            backend.close()


def worker_error(exc):
    result = {"status": "worker_error", **exception_details(exc)}
    if hasattr(exc, "evidence"):
        result["preparation"] = exc.evidence
    return redact_secrets(result)


if __name__ == "__main__":
    try:
        outcome = run(json.loads(sys.stdin.read()))
    except Exception as exc:
        outcome = worker_error(exc)
    print(MARKER + json.dumps(redact_secrets(outcome), ensure_ascii=True, allow_nan=False), flush=True)
    raise SystemExit(0 if outcome["status"] == "complete" else 1)
