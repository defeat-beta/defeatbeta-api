"""Call every query method for every US ticker and classify the errors.

`plan` freezes the catalog and the method list. `run` executes one shard of the
tickers in worker processes and appends one JSON line per ticker to its
progress file, so an interrupted shard resumes where it stopped.

A ValueError raised by defeatbeta_api itself is a business error, such as an
unknown industry. Any other exception is unexpected and is rechecked against
the previous release.
"""

import argparse
from collections import Counter
import json
import logging
import multiprocessing
from multiprocessing.connection import wait
from pathlib import Path
import sys
import time

from benchmark.common import redact_secrets
from benchmark.e2e import plan as e2e_plan
from benchmark.e2e.execution import invoke

PLAN_VERSION = 1
# Body methods read one record chosen from the result of their listing method.
BODY_SOURCES = {"transcript_body": "transcripts_list", "news_body": "news_list"}
ERROR_LENGTH = 500


def shard(symbols, index, count):
    """Return every count-th symbol of the sorted catalog, starting at index."""
    if count < 1 or not 0 <= index < count:
        raise ValueError("Shard index must be in [0, count)")
    return sorted(symbols)[index::count]


def _innermost_frame(exc):
    traceback = exc.__traceback__
    while traceback is not None and traceback.tb_next is not None:
        traceback = traceback.tb_next
    return traceback


def _site(frame, package_dir):
    path = Path(frame.tb_frame.f_code.co_filename).resolve()
    package_dir = Path(package_dir).resolve()
    if path.is_relative_to(package_dir):
        path = path.relative_to(package_dir.parent)
    return f"{path.as_posix()}:{frame.tb_lineno}"


def raise_site(exc, package_dir):
    """Where the exception was raised, relative to the package's parent when inside it."""
    frame = _innermost_frame(exc)
    return None if frame is None else _site(frame, package_dir)


def package_site(exc, package_dir):
    """The innermost frame inside the package, which locates errors raised by dependencies."""
    package_dir = Path(package_dir).resolve()
    traceback, found = exc.__traceback__, None
    while traceback is not None:
        if Path(traceback.tb_frame.f_code.co_filename).resolve().is_relative_to(package_dir):
            found = traceback
        traceback = traceback.tb_next
    return None if found is None else _site(found, package_dir)


def classify(exc, package_dir):
    frame = _innermost_frame(exc)
    inside = frame is not None and Path(frame.tb_frame.f_code.co_filename).resolve().is_relative_to(
        Path(package_dir).resolve())
    return "expected_error" if isinstance(exc, ValueError) and inside else "unexpected_error"


def body_kwargs(method, listing):
    """Parameters of the latest listed record, or None when there is none."""
    if listing is None or listing.empty:
        return None
    if method == "transcript_body":
        row = listing.sort_values(["fiscal_year", "fiscal_quarter"]).iloc[-1]
        return {"fiscal_year": int(row["fiscal_year"]), "fiscal_quarter": int(row["fiscal_quarter"])}
    row = listing.sort_values(["report_date", "uuid"]).iloc[-1]
    return {"uuid": str(row["uuid"])}


def _error_row(row, exc, package_dir):
    return {**row, "status": classify(exc, package_dir), "error_type": type(exc).__name__,
            "error": redact_secrets(str(exc))[:ERROR_LENGTH], "raised_at": raise_site(exc, package_dir),
            "package_site": package_site(exc, package_dir)}


def run_ticker(symbol, currency, methods, ticker_factory, package_dir):
    """Call every method once; bodies run after the listings they depend on."""
    try:
        ticker = ticker_factory(symbol)
    except Exception as exc:
        return [_error_row({"method": "__init__", "kwargs": {}, "seconds": None}, exc, package_dir)]
    listings, rows = {}, []
    for name in sorted(methods, key=lambda method: method in BODY_SOURCES):
        specification = methods[name]
        kwargs = dict(specification["kwargs"])
        if name == "currency":
            kwargs["symbol"] = f"{currency}=X" if currency and currency != "USD" else "EUR=X"
        if name in BODY_SOURCES:
            kwargs = body_kwargs(name, listings.get(BODY_SOURCES[name]))
            if kwargs is None:
                rows.append({"method": name, "kwargs": {}, "status": "not_applicable", "seconds": None})
                continue
        row = {"method": name, "kwargs": kwargs}
        started = time.perf_counter()
        try:
            value = invoke(ticker, {"call": specification["call"], "kwargs": kwargs})
        except Exception as exc:
            rows.append(_error_row({**row, "seconds": time.perf_counter() - started}, exc, package_dir))
            continue
        rows.append({**row, "status": "ok", "seconds": time.perf_counter() - started,
                     "rows": len(value) if hasattr(value, "__len__") else None})
        if name in BODY_SOURCES.values():
            listings[name] = value
    return rows


def product_work(symbol, currency, options):
    """Worker entry point: run one ticker against the installed defeatbeta_api."""
    import defeatbeta_api
    from defeatbeta_api.client.duckdb_conf import Configuration
    from defeatbeta_api.data.ticker import Ticker

    config = Configuration(cache_directory=options["cache_directory"])
    tickers = []

    def factory(name):
        tickers.append(Ticker(name, config=config, log_level=logging.WARNING))
        return tickers[-1]

    calls = run_ticker(symbol, currency, options["methods"], factory, Path(defeatbeta_api.__file__).parent)
    version = tickers[0].duckdb_client._data_update_time if tickers else None
    return {"dataset_version": version, "calls": calls}


def _serve(connection, work):
    while True:
        job = connection.recv()
        if job is None:
            return
        connection.send(work(*job))


def _finished(progress):
    if not progress.exists():
        return set()
    return {json.loads(line)["symbol"] for line in progress.read_text().splitlines() if line.strip()}


def run_shard(jobs, progress, *, processes, ticker_timeout, work, options, stop_after=None):
    """Run (symbol, currency) jobs in worker processes, one progress line per ticker.

    A worker that exceeds ticker_timeout is terminated and one that exits is
    replaced; its ticker is recorded as timeout or crashed. No new ticker
    starts after stop_after seconds; the rest is left for a later run.
    """
    progress = Path(progress)
    done = _finished(progress)
    pending = [job for job in jobs if job[0] not in done]
    summary = Counter(skipped=len(jobs) - len(pending))
    context = multiprocessing.get_context("spawn")
    started = time.monotonic()
    workers = {}  # connection -> [process, job, start time]

    def spawn():
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child, work), daemon=True)
        process.start()
        child.close()
        workers[parent] = [process, None, None]

    def record(job, status, seconds, result=None):
        line = {"symbol": job[0], "status": status, "seconds": seconds, **(result or {})}
        with progress.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, sort_keys=True, allow_nan=False, default=str) + "\n")
        summary[status] += 1

    def retire(connection):
        process = workers.pop(connection)[0]
        process.kill()
        process.join()
        connection.close()

    def accepting():
        return stop_after is None or time.monotonic() - started < stop_after

    queue = list(reversed(pending))
    try:
        for _ in range(min(processes, len(queue)) if accepting() else 0):
            spawn()
        while workers:
            for connection, state in workers.items():
                if state[1] is None and queue and accepting():
                    state[1], state[2] = queue.pop(), time.monotonic()
                    connection.send((*state[1], options))
            busy = [connection for connection, state in workers.items() if state[1] is not None]
            if not busy:
                break
            for connection in wait(busy, timeout=1):
                process, job, job_started = workers[connection]
                try:
                    result = connection.recv()
                except (EOFError, OSError):
                    record(job, "crashed", time.monotonic() - job_started)
                    retire(connection)
                    if queue and accepting():
                        spawn()
                    continue
                record(job, "done", time.monotonic() - job_started, result)
                workers[connection][1] = None
            now = time.monotonic()
            for connection, (process, job, job_started) in list(workers.items()):
                if job is not None and now - job_started > ticker_timeout:
                    record(job, "timeout", now - job_started)
                    retire(connection)
                    if queue and accepting():
                        spawn()
    finally:
        for connection in list(workers):
            try:
                connection.send(None)
            except OSError:
                pass
            retire(connection)
    summary["not_run"] = len(queue)
    return dict(summary)


def build_plan():
    from defeatbeta_api.data.company_meta import CompanyMeta
    from defeatbeta_api.data.ticker import Ticker

    meta = CompanyMeta(log_level=logging.WARNING)
    currencies = meta.get_financial_currency_map()
    return {"version": PLAN_VERSION, "dataset_version": meta.duckdb_client._data_update_time,
            "currencies": dict(sorted(currencies.items())), "methods": e2e_plan.query_methods(Ticker)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="Freeze the catalog and the method list")
    plan_parser.add_argument("--output", required=True)
    plan_parser.add_argument("--limit", type=int, help="Keep only the first N sorted tickers")
    run_parser = commands.add_parser("run", help="Run one shard of a plan")
    run_parser.add_argument("--plan", required=True)
    run_parser.add_argument("--shard", type=int, default=0)
    run_parser.add_argument("--shards", type=int, default=1)
    run_parser.add_argument("--output", required=True, help="Directory for progress.jsonl and the cache")
    run_parser.add_argument("--processes", type=int, default=4)
    run_parser.add_argument("--ticker-timeout", type=float, default=600)
    run_parser.add_argument("--stop-after", type=float, help="Start no ticker after this many seconds")
    args = parser.parse_args(argv)

    if args.command == "plan":
        value = build_plan()
        if args.limit:
            value["currencies"] = dict(list(value["currencies"].items())[:args.limit])
        Path(args.output).write_text(json.dumps(value, indent=1, sort_keys=True))
        print(f"{len(value['currencies'])} tickers, {len(value['methods'])} methods, "
              f"dataset {value['dataset_version']}")
        return 0
    value = json.loads(Path(args.plan).read_text())
    if value.get("version") != PLAN_VERSION:
        raise ValueError("Unsupported plan version")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    currencies = value["currencies"]
    jobs = [(symbol, currencies[symbol]) for symbol in shard(currencies, args.shard, args.shards)]
    options = {"methods": value["methods"], "cache_directory": str(output / "cache")}
    summary = run_shard(jobs, output / "progress.jsonl", processes=args.processes,
                        ticker_timeout=args.ticker_timeout, work=product_work, options=options,
                        stop_after=args.stop_after)
    print(json.dumps({"shard": args.shard, "shards": args.shards, "tickers": len(jobs), **summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
