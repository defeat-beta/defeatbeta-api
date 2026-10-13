"""Reproduce CPU consumption while synchronous fsspec reads are blocked.

Only local synthetic Parquet bytes are used. Every case runs in a disposable
process with a hard deadline. Thread counts are diagnostic controls, not product
recommendations. CPU ratios are observations, not portable correctness checks.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import tempfile
from threading import Event, Lock, get_ident, get_native_id
import time

import duckdb
from fsspec import AbstractFileSystem


ROWS = 32768


class ReadGate:
    def __init__(self, timeout=10):
        self.entered = Event()
        self.release = Event()
        self.lock = Lock()
        self.timeout = timeout
        self.caller_ident = None
        self.readers = []
        self.timeouts = 0

    def wait(self, offset, length):
        with self.lock:
            self.readers.append({"native_id": get_native_id(),
                                 "caller_owned": get_ident() == self.caller_ident,
                                 "offset": offset, "length": length})
        self.entered.set()
        if not self.release.wait(self.timeout):
            with self.lock:
                self.timeouts += 1
            raise TimeoutError("Synthetic read gate was not released")


class GatedFile(io.BytesIO):
    def __init__(self, payload, gate):
        super().__init__(payload)
        self.size = len(payload)
        self.gate = gate

    def read(self, size=-1):
        start = self.tell()
        end = self.size if size < 0 else min(self.size, start + size)
        # Do not block the magic-byte or tail/footer reads used in planning.
        if end - start > 8 and start < self.size // 2:
            self.gate.wait(start, end - start)
        return super().read(size)


class GatedFileSystem(AbstractFileSystem):
    protocol = "waitrepro"
    cachable = False

    def __init__(self, payload, gates):
        super().__init__()
        self.payload = payload
        self.gates = gates

    def info(self, path, **kwargs):
        name = self._strip_protocol(path)
        if name not in self.gates:
            raise FileNotFoundError(name)
        return {"name": name, "size": len(self.payload), "type": "file"}

    def modified(self, path):
        self.info(path)
        return datetime(2020, 1, 1, tzinfo=timezone.utc)

    def _open(self, path, mode="rb", **kwargs):
        if mode != "rb":
            raise ValueError("The synthetic filesystem is read-only")
        name = self._strip_protocol(path)
        return GatedFile(self.payload, self.gates[name])


def create_fixture(directory):
    path = Path(directory) / "fixture.parquet"
    connection = duckdb.connect(config={"threads": 1})
    try:
        connection.execute(
            f"COPY (SELECT i AS id, i * 3 + 7 AS value FROM range({ROWS}) t(i)) "
            "TO ? (FORMAT PARQUET, COMPRESSION UNCOMPRESSED, ROW_GROUP_SIZE 131072)",
            [str(path)])
    finally:
        connection.close()
    return path.read_bytes()


def _measure_case(payload, threads, queries, blocked_seconds, cancel):
    gates = {f"query-{index}.parquet": ReadGate() for index in range(queries)}
    filesystem = GatedFileSystem(payload, gates)
    connection = duckdb.connect(config={"threads": threads, "enable_external_file_cache": False})
    connection.register_filesystem(filesystem)
    cursors = [connection.cursor() for _ in range(queries)]
    pool = ThreadPoolExecutor(max_workers=queries)
    completed = [Event() for _ in range(queries)]
    expected_count = ROWS // 2
    expected = [3 * expected_count * (expected_count - 1) + 7 * expected_count, expected_count]

    def query(index):
        gate = gates[f"query-{index}.parquet"]
        gate.caller_ident = get_ident()
        started = time.monotonic()
        cpu_started = time.thread_time()
        try:
            effective_threads = cursors[index].execute(
                "SELECT current_setting('threads')").fetchone()[0]
            if effective_threads != threads:
                raise AssertionError("Requested thread count was not applied to the cursor")
            rows = cursors[index].sql(
                f"SELECT sum(value), count(*) FROM 'waitrepro://query-{index}.parquet' "
                "WHERE id % 2 = 0").fetchall()
            return {"status": "ok", "result": list(rows[0]),
                    "effective_threads": effective_threads,
                    "wall_seconds": time.monotonic() - started,
                    "caller_cpu_seconds": time.thread_time() - cpu_started}
        except Exception as exc:
            return {"status": "error", "error_type": type(exc).__name__,
                    "error": str(exc),
                    "wall_seconds": time.monotonic() - started,
                    "caller_cpu_seconds": time.thread_time() - cpu_started}
        finally:
            completed[index].set()

    try:
        futures = [pool.submit(query, index) for index in range(queries)]
        deadline = time.monotonic() + 5
        for index, gate in enumerate(gates.values()):
            while not gate.entered.wait(0.01):
                if futures[index].done():
                    raise AssertionError(f"Query ended before its data read: {futures[index].result()}")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Query did not reach a synthetic data read")
        if any(event.is_set() for event in completed):
            raise AssertionError("Query completed before its data was released")
        started = time.monotonic()
        cpu_started = time.process_time()
        Event().wait(blocked_seconds)
        cpu = time.process_time() - cpu_started
        elapsed = time.monotonic() - started
        blocked_readers = []
        for gate in gates.values():
            with gate.lock:
                blocked_readers.append(list(gate.readers))
        interrupt_seconds = None
        finished_before_release = None
        if cancel:
            started_interrupt = time.monotonic()
            cursors[0].interrupt()
            interrupt_seconds = time.monotonic() - started_interrupt
            finished_before_release = completed[0].wait(0.1)
        for gate in gates.values():
            gate.release.set()
        released = time.monotonic()
        results = [future.result(timeout=5) for future in futures]
        recovery = cursors[0].execute("SELECT 42").fetchone()[0] if cancel else None
        for index, result in enumerate(results):
            if cancel and index == 0:
                if result.get("error_type") != "InterruptException":
                    raise AssertionError(f"Cancelled query returned {result}")
            elif result.get("result") != expected or result["status"] != "ok":
                raise AssertionError(f"Unexpected query result: {result}")
        if any(gate.timeouts for gate in gates.values()):
            raise AssertionError("Read gate timed out")
        return {"threads": threads, "queries": queries, "cancel": cancel,
                "requested_block_seconds": blocked_seconds,
                "blocked_wall_seconds": elapsed, "blocked_cpu_seconds": cpu,
                "blocked_cpu_per_wall": cpu / elapsed,
                "readers_at_end_of_block": blocked_readers, "results": results,
                "interrupt_call_seconds": interrupt_seconds,
                "cancelled_finished_before_release": finished_before_release,
                "completion_after_release_seconds": time.monotonic() - released,
                "cancelled_cursor_recovery": recovery}
    finally:
        for gate in gates.values():
            gate.release.set()
        pool.shutdown(wait=True)
        for cursor in cursors:
            cursor.close()
        connection.close()


def _worker(channel, payload, options):
    try:
        channel.send({"result": _measure_case(payload, **options)})
    except BaseException as exc:
        channel.send({"error_type": type(exc).__name__, "error": str(exc)})
    finally:
        channel.close()


def run_case(payload, *, threads=4, queries=1, blocked_seconds=0.3, cancel=False, timeout=20):
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(writer, payload, {
        "threads": threads, "queries": queries,
        "blocked_seconds": blocked_seconds, "cancel": cancel}))
    process.start()
    writer.close()
    try:
        if not reader.poll(timeout):
            raise TimeoutError("Isolated query reproduction exceeded its deadline")
        response = reader.recv()
        if "error_type" in response:
            raise RuntimeError(f"{response['error_type']}: {response['error']}")
        process.join(timeout=3)
        if process.is_alive() or process.exitcode != 0:
            raise RuntimeError("Isolated query process did not exit cleanly")
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
    parser.add_argument("--threads", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--queries", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--delays", nargs="+", type=float, default=[0.3, 0.9])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    if (min(args.threads + args.queries + [args.repeats]) < 1
            or any(not 0 < delay <= 3 for delay in args.delays)):
        parser.error("Counts must be positive and delays must be within (0, 3] seconds")
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "duckdb_version": duckdb.__version__,
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "methodology": {
                  "network": "None; in-memory synthetic Parquet via fsspec",
                  "cpu": "Process CPU delta only while data reads are held behind an Event",
                  "ownership": "Reader identity compared with the query caller; scheduling is not forced",
                  "isolation": "Fresh spawned process and DuckDB database per case; hard parent deadline",
                  "cancellation": "Interrupt query zero while reads remain blocked, then release all reads",
                  "scope": "Dependency reproduction only; no DefeatBeta transport or cache imported"},
              "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")

    try:
        with tempfile.TemporaryDirectory() as directory:
            payload = create_fixture(directory)
        report["fixture_sha256"] = hashlib.sha256(payload).hexdigest()
        report["fixture_bytes"] = len(payload)
        for threads in args.threads:
            for queries in args.queries:
                for delay in args.delays:
                    for repeat in range(args.repeats):
                        case = run_case(payload, threads=threads, queries=queries,
                                        blocked_seconds=delay, cancel=args.cancel)
                        case["repeat"] = repeat + 1
                        report["cases"].append(case)
                        save()
                        owners = sum(any(r["caller_owned"] for r in readers)
                                     for readers in case["readers_at_end_of_block"])
                        print(f"threads={threads} queries={queries} delay={delay} "
                              f"caller_owned={owners} cpu/wall={case['blocked_cpu_per_wall']:.3f}", flush=True)
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
