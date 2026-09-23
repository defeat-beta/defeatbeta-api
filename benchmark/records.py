"""Compact JSON records, explicit archival, and bounded local retention."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tempfile

SHARED_FIELDS = {
    "environment", "configured_settings", "methodology", "result",
    "effective_settings", "loaded_extensions",
}
CONSISTENT_ARCHIVE_FIELDS = {
    "environment", "configured_settings", "methodology", "revision", "tag",
    "requested_runs", "timeout_seconds", "resolve_direct", "suite_id",
}
COMPARABLE_FIELDS = {
    "environment", "methodology", "revision", "requested_runs",
    "timeout_seconds", "suite_symbols", "schedule", "url", "sql",
}


def pack_reports(reports):
    shared = {}
    identifiers = {}

    def encode(value):
        if isinstance(value, list):
            return [encode(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in SHARED_FIELDS:
                signature = json.dumps(item, sort_keys=True)
                if signature not in identifiers:
                    identifier = f"{key}_{len(shared) + 1}"
                    identifiers[signature] = identifier
                    shared[identifier] = item
                result[key] = {"$ref": identifiers[signature]}
            else:
                result[key] = encode(item)
        return result

    runs = encode(reports)
    return {"format_version": 2, "shared": shared, "runs": runs}


def unpack_reports(record):
    if record.get("format_version") != 2:
        raise ValueError("Unsupported record format")

    def decode(value):
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                return record["shared"][value["$ref"]]
            return {key: decode(item) for key, item in value.items()}
        return value

    return decode(record["runs"])


def write_record(path, reports):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(pack_reports(reports), handle, indent=2)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive_reports(reports):
    if not reports or any(report.get("status") != "complete" for report in reports):
        raise ValueError("Only complete benchmark runs can be archived")
    for field in CONSISTENT_ARCHIVE_FIELDS:
        signatures = {
            json.dumps(report.get(field), sort_keys=True)
            for report in reports
        }
        if len(signatures) > 1:
            raise ValueError(f"Archive mixes different {field} values")


def _report_results_by_symbol(reports):
    results = {}
    for report in reports:
        symbol = report.get("symbol")
        if not symbol or symbol in results:
            raise ValueError("Each archived run must contain unique symbols")
        signatures = {
            json.dumps(sample.get("result"), sort_keys=True)
            for sample in report.get("samples", [])
            if sample.get("status") == "ok"
        }
        if len(signatures) != 1:
            raise ValueError(f"Run has inconsistent results for {symbol}")
        results[symbol] = signatures.pop()
    return results


def validate_comparison(baseline_reports, candidate_reports, allowed_setting_differences=()):
    """Validate two complete runs before publishing one comparison archive."""
    validate_archive_reports(baseline_reports)
    validate_archive_reports(candidate_reports)

    baseline = baseline_reports[0]
    candidate = candidate_reports[0]
    for field in COMPARABLE_FIELDS:
        if baseline.get(field) != candidate.get(field):
            raise ValueError(f"Comparison has different {field} values")

    allowed = set(allowed_setting_differences)
    baseline_settings = baseline.get("configured_settings", {})
    candidate_settings = candidate.get("configured_settings", {})
    setting_names = set(baseline_settings) | set(candidate_settings)
    changed_settings = {
        name for name in setting_names
        if baseline_settings.get(name) != candidate_settings.get(name)
    }
    unexpected = changed_settings - allowed
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise ValueError(f"Comparison has undeclared setting differences: {names}")
    unused = allowed - changed_settings
    if unused:
        names = ", ".join(sorted(unused))
        raise ValueError(f"Declared setting differences did not change: {names}")

    baseline_results = _report_results_by_symbol(baseline_reports)
    candidate_results = _report_results_by_symbol(candidate_reports)
    if baseline_results != candidate_results:
        raise ValueError("Comparison result hashes or symbols do not match")


def pack_comparison(baseline_reports, candidate_reports, allowed_setting_differences=()):
    validate_comparison(
        baseline_reports,
        candidate_reports,
        allowed_setting_differences=allowed_setting_differences,
    )
    return {
        "format_version": 3,
        "allowed_setting_differences": sorted(allowed_setting_differences),
        "baseline": pack_reports(baseline_reports),
        "candidate": pack_reports(candidate_reports),
    }


def unpack_comparison(record):
    if record.get("format_version") != 3:
        raise ValueError("Unsupported comparison format")
    baseline_reports = unpack_reports(record["baseline"])
    candidate_reports = unpack_reports(record["candidate"])
    validate_comparison(
        baseline_reports,
        candidate_reports,
        allowed_setting_differences=record.get("allowed_setting_differences", []),
    )
    return baseline_reports, candidate_reports


def _validate_archive_name(name):
    if not re.fullmatch(r"[0-9]{3}_[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("Archive name must look like 001_connection_reuse")


def archive_record(source, output, name):
    """Archive one legacy standalone run; the CLI publishes comparisons."""
    _validate_archive_name(name)
    source = Path(source)
    record = json.loads(source.read_text(encoding="utf-8"))
    reports = unpack_reports(record)
    validate_archive_reports(reports)
    destination = Path(output) / "archive" / f"{name}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects previously cited evidence from replacement.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    return destination


def archive_comparison(baseline_source, candidate_source, output, name,
                       allowed_setting_differences=()):
    """Publish one immutable baseline-versus-candidate evidence record."""
    _validate_archive_name(name)
    baseline_record = json.loads(Path(baseline_source).read_text(encoding="utf-8"))
    candidate_record = json.loads(Path(candidate_source).read_text(encoding="utf-8"))
    comparison = pack_comparison(
        unpack_reports(baseline_record),
        unpack_reports(candidate_record),
        allowed_setting_differences=allowed_setting_differences,
    )
    destination = Path(output) / "archive" / f"{name}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(comparison, handle, indent=2)
        handle.write("\n")
    return destination


def prune_local(output, days=30, count=100, now=None):
    now = now or datetime.now(timezone.utc)
    candidates = []
    for path in (Path(output) / "local").glob("*.json"):
        if path.is_symlink():
            continue
        try:
            created = datetime.strptime(path.name.split("_", 1)[0], "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
            reports = unpack_reports(json.loads(path.read_text(encoding="utf-8")))
            if not reports:
                continue
            if any(report["status"] == "running" for report in reports) and created >= now - timedelta(days=days):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        candidates.append((created, path))
    removed = []
    for index, (created, path) in enumerate(sorted(candidates, reverse=True)):
        if index >= count or created < now - timedelta(days=days):
            path.unlink()
            removed.append(path)
    return removed
