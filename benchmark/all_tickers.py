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
        if not hasattr(ticker, specification["call"].split(".")[0]):
            rows.append({**row, "status": "missing_method", "seconds": None})
            continue
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


def select_methods(methods, names):
    """The named methods plus the listings their bodies need; None selects all."""
    if names is None:
        return methods
    wanted = set(names) | {BODY_SOURCES[name] for name in names if name in BODY_SOURCES}
    return {name: methods[name] for name in sorted(wanted) if name in methods}


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

    methods = select_methods(options["methods"], options.get("only", {}).get(symbol))
    calls = run_ticker(symbol, currency, methods, factory, Path(defeatbeta_api.__file__).parent)
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


FAILED = ("unexpected_error", "timeout", "crashed")
ERRORS = ("expected_error", "unexpected_error")
VERDICTS = ("regression", "not_rechecked", "pre_existing", "business_error")


def load_progress(directory):
    """Every progress line below directory; shards hold disjoint tickers."""
    lines = {}
    for path in sorted(Path(directory).rglob("progress.jsonl")):
        for text in path.read_text(encoding="utf-8").splitlines():
            if text.strip():
                value = json.loads(text)
                lines[value["symbol"]] = value
    return list(lines.values())


def recheck_selection(lines):
    """Tickers to rerun on the baseline: their erroring methods, or all (None) when the ticker failed."""
    selection = {}
    for line in lines:
        if line["status"] != "done":
            selection[line["symbol"]] = None
            continue
        methods = sorted(call["method"] for call in line["calls"] if call["status"] in ERRORS)
        if methods:
            selection[line["symbol"]] = methods
    return selection


def _rank(status):
    return 2 if status in FAILED else 1 if status == "expected_error" else 0


def verdict(candidate, baseline):
    """Compare one candidate outcome with the baseline outcome of the same call."""
    if baseline is None:
        return "not_rechecked"
    if baseline == "missing_method":
        return "regression" if candidate in FAILED else "business_error"
    if _rank(candidate) > _rank(baseline):
        return "regression"
    return "pre_existing" if candidate in FAILED else "business_error"


def _baseline_status(line, method):
    if line is None:
        return None
    if line["status"] != "done":
        return line["status"]
    if method == "__ticker__":
        return "unexpected_error" if any(call["status"] in FAILED for call in line["calls"]) else "ok"
    for call in line["calls"]:
        if call["method"] == method:
            return call["status"]
    # A constructor row exists only when construction failed.
    return "ok" if method == "__init__" else None


def compare(candidate, baseline, *, planned):
    baseline = {line["symbol"]: line for line in baseline}
    calls, tickers, groups = Counter(), Counter(), {}
    for line in sorted(candidate, key=lambda value: value["symbol"]):
        symbol, other = line["symbol"], baseline.get(line["symbol"])
        tickers[line["status"]] += 1
        if line["status"] != "done":
            outcomes = [{"method": "__ticker__", "status": line["status"], "error_type": line["status"]}]
        else:
            calls.update(call["status"] for call in line["calls"])
            outcomes = [call for call in line["calls"] if call["status"] in ERRORS]
        for call in outcomes:
            baseline_status = _baseline_status(other, call["method"])
            result = verdict(call["status"], baseline_status)
            site = call.get("package_site") or call.get("raised_at")
            group = groups.setdefault((result, call["method"], call.get("error_type"), site), {
                "verdict": result, "method": call["method"], "error_type": call.get("error_type"),
                "site": site, "tickers": [], "error": call.get("error"), "baseline": Counter()})
            group["tickers"].append(symbol)
            group["baseline"][baseline_status or "missing"] += 1
    groups = sorted(groups.values(), key=lambda group: (
        VERDICTS.index(group["verdict"]), -len(group["tickers"]), group["method"], str(group["site"])))
    for group in groups:
        group["baseline"] = dict(group["baseline"])
    verdicts = Counter()
    for group in groups:
        verdicts[group["verdict"]] += len(group["tickers"])
    missing = sorted(set(planned) - {line["symbol"] for line in candidate})
    status = ("incomplete" if missing or verdicts["not_rechecked"] else
              "fail" if verdicts["regression"] else "pass")
    return {"status": status, "planned_tickers": len(planned), "missing_tickers": missing,
            "tickers": dict(tickers), "calls": dict(calls), "verdicts": dict(verdicts),
            "candidate_dataset_versions": sorted({str(line.get("dataset_version")) for line in candidate}),
            "baseline_dataset_versions": sorted({str(line.get("dataset_version")) for line in baseline.values()}),
            "groups": groups}


SECTIONS = {"regression": "Regressions", "not_rechecked": "Not rechecked",
            "pre_existing": "Pre-existing errors", "business_error": "Business errors"}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(report, *, examples=10):
    lines = ["# All-tickers functional test", "", f"Status: {report['status']}", "",
             f"- Tickers: {report['planned_tickers']} planned; " +
             ", ".join(f"{count} {name}" for name, count in sorted(report["tickers"].items())),
             "- Calls: " + ", ".join(f"{count} {name}" for name, count in sorted(report["calls"].items())),
             f"- Dataset versions: candidate {', '.join(report['candidate_dataset_versions'])}; "
             f"baseline {', '.join(report['baseline_dataset_versions']) or 'none'}"]
    if report["missing_tickers"]:
        lines.append(f"- Tickers without a result: {len(report['missing_tickers'])} "
                     f"({', '.join(report['missing_tickers'][:examples])})")
    lines += ["", "A regression is a call whose result got worse than in the baseline: an error where the "
              "baseline returned data, or an unexpected error where the baseline raised a business error. "
              "Pre-existing errors fail the same way in both versions and do not fail the test."]
    for name, title in SECTIONS.items():
        groups = [group for group in report["groups"] if group["verdict"] == name]
        if not groups:
            continue
        lines += ["", f"## {title}", "", "| Method | Error | Site | Tickers | Examples | Message |",
                  "| --- | --- | --- | ---: | --- | --- |"]
        for group in groups:
            site = f"`{group['site']}`" if group["site"] else ""
            lines.append(f"| {group['method']} | {group['error_type']} | {site} | {len(group['tickers'])} | "
                         f"{', '.join(group['tickers'][:examples])} | {_cell(group['error'] or '')[:160]} |")
    return "\n".join(lines) + "\n"


def recheck(plan, candidate, output, baseline_ref, processes, ticker_timeout):
    """Rerun the candidate's errors on the baseline release; return the baseline progress lines."""
    from argparse import Namespace
    import subprocess

    from benchmark.benchmark import prepare, worker_environment

    selection = recheck_selection(candidate)
    if not selection:
        return []
    recheck_plan = {**plan, "currencies": {symbol: plan["currencies"].get(symbol) for symbol in selection},
                    "only": selection}
    (output / "recheck-plan.json").write_text(json.dumps(recheck_plan, indent=1, sort_keys=True))
    experiment = prepare(Namespace(output=output / "experiment", baseline=baseline_ref, candidate=None,
                                   baseline_lock=None))
    manifest = json.loads((experiment / "experiment.json").read_text(encoding="utf-8"))
    environment = manifest["environments"]["baseline"]
    subprocess.run([environment["python"], "-m", "benchmark.all_tickers", "run",
                    "--plan", str(output / "recheck-plan.json"), "--output", str(output / "baseline"),
                    "--processes", str(processes), "--ticker-timeout", str(ticker_timeout)],
                   cwd=environment["source"], env=worker_environment(experiment), check=True)
    return load_progress(output / "baseline")


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
    compare_parser = commands.add_parser("compare", help="Recheck errors on the baseline and write the report")
    compare_parser.add_argument("--plan", required=True)
    compare_parser.add_argument("--candidate", required=True, help="Directory holding the shards' progress")
    compare_parser.add_argument("--output", required=True)
    compare_parser.add_argument("--baseline", default="release-0.0.62")
    compare_parser.add_argument("--processes", type=int, default=4)
    compare_parser.add_argument("--ticker-timeout", type=float, default=600)
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
    if args.command == "compare":
        candidate = load_progress(args.candidate)
        baseline = recheck(value, candidate, output.resolve(), args.baseline, args.processes,
                           args.ticker_timeout)
        report = compare(candidate, baseline, planned=set(value["currencies"]))
        report.update(baseline_ref=args.baseline, plan_dataset_version=value["dataset_version"])
        (output / "results.json").write_text(json.dumps(report, indent=1, sort_keys=True))
        (output / "results.md").write_text(render(report))
        print(f"Status: {report['status']}; verdicts {report['verdicts']}")
        return 0 if report["status"] == "pass" else 1
    currencies = value["currencies"]
    jobs = [(symbol, currencies[symbol]) for symbol in shard(currencies, args.shard, args.shards)]
    options = {"methods": value["methods"], "only": value.get("only", {}),
               "cache_directory": str(output / "cache")}
    summary = run_shard(jobs, output / "progress.jsonl", processes=args.processes,
                        ticker_timeout=args.ticker_timeout, work=product_work, options=options,
                        stop_after=args.stop_after)
    print(json.dumps({"shard": args.shard, "shards": args.shards, "tickers": len(jobs), **summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
