"""Measure the compute cost of caller-only versus parallel DuckDB execution.

Use a shared in-memory database and separate cursors for concurrent callers.
Only measured query execution contributes to CPU and wall times. Each case
runs in a disposable process; no network or DefeatBeta transport is involved.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import platform
import statistics
from threading import Barrier
import time

import duckdb


PERIOD = 4096
GROUPS = 64
QUERY = """
SELECT value % 64 AS bucket,
       sum((value * value + 17 * value) % 1000003) AS checksum,
       count(*) AS rows
FROM fixture GROUP BY bucket ORDER BY bucket
"""


def expected_result(rows):
    """Compute integer aggregates from periodic frequencies, without SQL."""
    totals = {}
    whole, remainder = divmod(rows, PERIOD)
    for value in range(PERIOD):
        count = whole + (value < remainder)
        if count:
            group = totals.setdefault(value % GROUPS, [0, 0])
            group[0] += ((value * value + 17 * value) % 1000003) * count
            group[1] += count
    return [(bucket, *totals[bucket]) for bucket in sorted(totals)]


def _measure(threads, queries, rows):
    connection = duckdb.connect(config={"threads": 1})
    cursors = []
    try:
        # Identical fixture construction across candidates, outside measurement.
        connection.execute(
            f"CREATE TABLE fixture AS SELECT i % {PERIOD} AS value FROM range(?) t(i)", [rows])
        connection.execute(f"SET threads = {threads}")
        effective = connection.execute("SELECT current_setting('threads')").fetchone()[0]
        expected = expected_result(rows)
        if connection.sql(QUERY).fetchall() != expected:
            raise AssertionError("Warmup aggregate differs from the independent reference")
        cursors = [connection.cursor() for _ in range(queries)]
        barrier = Barrier(queries + 1)

        def query(index):
            barrier.wait(timeout=30)
            started = time.perf_counter()
            cpu_started = time.thread_time()
            result = cursors[index].sql(QUERY).fetchall()
            return {"seconds": time.perf_counter() - started,
                    "caller_cpu_seconds": time.thread_time() - cpu_started,
                    "result": result}

        with ThreadPoolExecutor(max_workers=queries) as executor:
            futures = [executor.submit(query, index) for index in range(queries)]
            started = time.perf_counter()
            cpu_started = time.process_time()
            barrier.wait(timeout=30)
            results = [future.result(timeout=60) for future in futures]
            cpu = time.process_time() - cpu_started
            elapsed = time.perf_counter() - started
        for result in results:
            if result.pop("result") != expected:
                raise AssertionError("Measured aggregate differs from the independent reference")
        durations = sorted(item["seconds"] for item in results)
        return {"threads": effective, "queries": queries, "rows_per_query": rows,
                "cpu_seconds": cpu, "wall_seconds": elapsed,
                "queries_per_second": queries / elapsed if elapsed > 0 else None,
                "p50_seconds": statistics.median(durations),
                "p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1],
                "result_sha256": hashlib.sha256(json.dumps(expected).encode()).hexdigest(),
                "results": results}
    finally:
        for cursor in cursors:
            cursor.close()
        connection.close()


def _worker(channel, options):
    try:
        channel.send({"result": _measure(**options)})
    except BaseException as exc:
        channel.send({"error_type": type(exc).__name__, "error": str(exc)})
    finally:
        channel.close()


def run_case(*, threads=4, queries=1, rows=8388608, timeout=120):
    if min(threads, queries, rows, timeout) <= 0:
        raise ValueError("Threads, queries, rows and timeout must be positive")
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(writer, {
        "threads": threads, "queries": queries, "rows": rows}))
    process.start()
    writer.close()
    try:
        if not reader.poll(timeout):
            raise TimeoutError("CPU comparison exceeded its process deadline")
        response = reader.recv()
        if "error_type" in response:
            raise RuntimeError(f"{response['error_type']}: {response['error']}")
        process.join(timeout=3)
        if process.is_alive() or process.exitcode != 0:
            raise RuntimeError("CPU comparison process did not exit cleanly")
        return response["result"]
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join()
        reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, nargs="+", default=[4, 1])
    parser.add_argument("--queries", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--rows", type=int, default=8388608)
    parser.add_argument("--rounds", type=int, default=6)
    args = parser.parse_args()
    if min(args.threads + args.queries + [args.rows, args.rounds]) < 1:
        parser.error("Counts must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the artifact before starting any work; never overwrite evidence.
    with args.output.open("x") as output:
        output.write("{}\n")
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "duckdb_version": duckdb.__version__, "python_version": platform.python_version(),
              "platform": platform.platform(), "rows": args.rows, "rounds": args.rounds,
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "sql": QUERY, "methodology": {
                  "fixture": "In-memory BIGINT table; one full warmup; no network or filesystem reads",
                  "order": "Reverse thread and query-concurrency order in alternate rounds",
                  "isolation": "Fresh spawned process and database per case, with a hard deadline",
                  "measurement": "Synchronized callers; setup, warmup, validation and shutdown excluded",
                  "validation": "Exact integer aggregates independently derived from value frequencies",
                  "scope": "Compute-heavy control; not a substitute for real API workloads"}, "cases": []}

    def save():
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")

    try:
        for round_number in range(args.rounds):
            threads = args.threads if round_number % 2 == 0 else list(reversed(args.threads))
            queries = args.queries if round_number % 2 == 0 else list(reversed(args.queries))
            for concurrency in queries:
                for count in threads:
                    case = run_case(threads=count, queries=concurrency, rows=args.rows)
                    case["round"] = round_number + 1
                    report["cases"].append(case)
                    save()
                    print(f"round={round_number + 1} threads={count} queries={concurrency} "
                          f"wall={case['wall_seconds']:.4f} cpu={case['cpu_seconds']:.4f} "
                          f"p95={case['p95_seconds']:.4f}", flush=True)
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
