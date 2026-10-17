"""Run the frozen end-to-end contract inside one isolated product interpreter."""

import json
from pathlib import Path
import sys

from benchmark.support.adapter import dataset_endpoint
from benchmark.common import environment_info, redact_secrets, source_hashes
from benchmark.e2e.backend import ProductBackend, discover
from benchmark.e2e.execution import measure_latency, measure_throughput
from benchmark.e2e.plan import query_methods


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
    backend = ProductBackend(payload["cache_directory"], workload)
    with dataset_endpoint(payload.get("endpoint")):
        try:
            if payload["action"] == "discover":
                return {"status": "complete", "plan": discover(backend)}
            available = query_methods(Ticker)
            missing = set(workload["methods"]) - set(available)
            if missing:
                raise ValueError(f"Product does not implement frozen query operations: {sorted(missing)}")
            phase = payload["phase"]
            if phase["kind"] == "latency":
                progress = Path(payload.get("progress_path", Path(payload["cache_directory"]).parent / "progress.jsonl"))
                progress.parent.mkdir(parents=True, exist_ok=True)
                with progress.open("w", encoding="utf-8") as stream:
                    def emit(row):
                        stream.write(json.dumps(redact_secrets(row), ensure_ascii=True, allow_nan=False) + "\n")
                        stream.flush()
                    result = measure_latency(workload, backend, phase["state"], emit=emit)
            else:
                result = measure_throughput(workload, backend, phase["state"], phase["concurrency"])
            if phase["state"] == "cached":
                backend.seed.validate()
            result["cache_settings"] = backend.settings()
            result["api_coverage"] = available
            result["observed_dataset"] = backend.dataset()
            return result
        finally:
            backend.close()


if __name__ == "__main__":
    try:
        outcome = run(json.loads(sys.stdin.read()))
    except Exception as exc:
        outcome = {"status": "worker_error", "error_type": type(exc).__name__,
                   "error": redact_secrets(str(exc))}
    print(MARKER + json.dumps(redact_secrets(outcome), ensure_ascii=True, allow_nan=False), flush=True)
    raise SystemExit(0 if outcome["status"] == "complete" else 1)
