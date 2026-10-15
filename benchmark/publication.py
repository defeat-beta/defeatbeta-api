"""Validate one complete workflow run and package immutable release evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from benchmark.common import save_json
from benchmark.report import render, summarize
from benchmark.suite import make_suite


REQUIRED_EXPERIMENTS = {("controlled", "h2"), ("live", None)}


def validate_run(run, repository):
    """Only a successful manual benchmark from this repository can be promoted."""
    if (run["repository"]["full_name"] != repository
            or run["path"] != ".github/workflows/benchmark.yml"
            or run["event"] != "workflow_dispatch"
            or run["status"] != "completed" or run["conclusion"] != "success"):
        raise ValueError("Select a successful manual benchmark workflow from this repository")


def validate_record(record, candidate, run):
    if not summarize(record)["valid"]:
        raise ValueError("Incomplete or invalid comparison cannot become a release report")
    plan = make_suite("release")
    # Discovery may add body identifiers, but it cannot drop or substitute workload tasks.
    actual = record["suite"]
    for key in ("name", "version", "seed", "sha256", "symbols", "methods", "cache_policy"):
        if actual.get(key) != plan[key]:
            raise ValueError("A complete standard release suite is required")
    if len(actual["cases"]) != len(plan["cases"]):
        raise ValueError("A complete standard release suite is required")
    for measured, expected in zip(actual["cases"], plan["cases"]):
        for key in ("id", "kind", "state", "concurrency", "cache_policy"):
            if measured.get(key) != expected[key]:
                raise ValueError("Release workload differs from the declared suite")
        tasks = [{"symbol": task["symbol"], "method": task["method"]} for task in measured["tasks"]]
        if tasks != expected["tasks"]:
            raise ValueError("Release tasks differ from the declared suite")
    digest = hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
    if record.get("resolved_suite_sha256") != digest:
        raise ValueError("Resolved suite checksum mismatch")
    if record["rounds"] < 6 or record["rounds"] % 2:
        raise ValueError("Release evidence requires at least six balanced paired rounds")
    environment = record["experiment"]["environments"]["candidate"]
    if environment["commit"] != candidate:
        raise ValueError("Release tag does not identify the measured candidate commit")
    workflow = record.get("workflow", {})
    if (workflow.get("repository") != run["repository"]["full_name"]
            or str(workflow.get("run_id")) != str(run["id"])
            or str(workflow.get("run_attempt")) != str(run["run_attempt"])
            or workflow.get("sha") != run["head_sha"]):
        raise ValueError("Evidence does not belong to the selected workflow attempt")


def finalize(source, output, release, candidate, run):
    """Create a bundle without executing downloaded code or repeating measurements."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", release):
        raise ValueError("Release tag must be a simple filename-safe identifier")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("The release candidate must be a full Git commit")
    validate_run(run, run["repository"]["full_name"])
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError("Publication destination already exists")
    selected = {}
    identity = None
    for path in sorted(source.rglob("results.json")):
        record = json.loads(path.read_text())
        validate_record(record, candidate, run)
        key = (record["mode"], record.get("protocol_control"))
        if key not in REQUIRED_EXPERIMENTS or key in selected:
            raise ValueError("Select exactly one fixed-data H2 and one live-service experiment")
        manifest = record["experiment"]
        shared = {"harness": manifest["harness"], "harness_dependency_lock": manifest["harness_dependency_lock"],
                  "rounds": record["rounds"],
                  "environments": {name: {field: env[field] for field in
                      ("commit", "source_hashes", "dependency_lock")}
                      for name, env in manifest["environments"].items()}}
        if identity is not None and identity != shared:
            raise ValueError("Experiments use different sources, dependencies, harnesses, or rounds")
        identity = shared
        selected[key] = (path, record)
    if set(selected) != REQUIRED_EXPERIMENTS:
        raise ValueError("Fixed-data and live-service experiments are required")

    # Downloaded source is evidence only. Read and copy verified files; never import it.
    sample_path, sample = selected[("controlled", "h2")]
    harness_root = sample_path.parent.parent / "harness" / "benchmark"
    harness_files = {}
    for relative, expected_hash in identity["harness"].items():
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative:
            raise ValueError("Invalid harness evidence path")
        path = harness_root / relative
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(harness_root.resolve()):
            raise ValueError("Missing harness source evidence")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("Harness evidence checksum mismatch")
        harness_files[relative] = content
    if not harness_files:
        raise ValueError("Harness source evidence is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="benchmark-publication-") as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        lines = [f"# Performance report for {release}", "", "Stage: **final release report**.", "",
                 f"Candidate: `{candidate}`.",
                 f"Baseline: `{identity['environments']['baseline']['commit']}`.", "",
                 f"Source: {run['html_url']} (attempt {run['run_attempt']}).", "",
                 "Each experiment compares A/B on one runner. Do not compare absolute times across jobs.",
                 "All samples from the selected run are retained, including inconclusive or slower cases.", "",
                 "| Experiment | Faster cases | Slower cases | Inconclusive cases |",
                 "| --- | ---: | ---: | ---: |"]
        for key, (path, record) in sorted(selected.items()):
            name = "live-service" if key[0] == "live" else "fixed-data"
            folder = staging / name
            folder.mkdir()
            target = folder / "results.json"
            shutil.copyfile(path, target)
            summary = render(target, release=release)
            counts = {label: sum(row["classification"] == label for row in summary["cases"])
                      for label in ("faster in this run", "slower in this run", "inconclusive")}
            lines.append(f"| [{name}]({name}/results.md) | {counts['faster in this run']} | "
                         f"{counts['slower in this run']} | {counts['inconclusive']} |")
        for relative, content in harness_files.items():
            target = staging / "harness" / "benchmark" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for variant, env in sample["experiment"]["environments"].items():
            (staging / f"{variant}-dependencies.lock").write_text(env["dependency_lock"], encoding="utf-8")
        (staging / "harness-dependencies.lock").write_text(identity["harness_dependency_lock"], encoding="utf-8")
        lines += ["", "The ratios describe this workload and environment; there is no universal speedup claim.",
                  "Live data follows the current remote main revision. Historical HF revisions are not required.",
                  "Read each report's limitations and raw evidence before interpreting the comparison.", "",
                  "The bundle includes the measurement harness and dependency locks. Follow benchmark/README.md",
                  "in the source checkout to recreate isolated environments. All evidence files are checksummed",
                  "in publication.json. Finalization renders saved evidence; it never reruns queries.", ""]
        (staging / "README.md").write_text("\n".join(lines), encoding="utf-8")
        evidence_url = (f"https://github.com/{run['repository']['full_name']}/releases/download/"
                        f"{release}/performance-evidence.tar.gz")
        standalone = [f"# Performance report for {release}", "",
                      f"Candidate: `{candidate}`. Source run: {run['html_url']}.", "",
                      f"[Download the complete evidence bundle]({evidence_url}).", ""]
        for report_path in sorted(staging.glob("*/results.md")):
            content = report_path.read_text()
            content = content.replace("# Paired API performance report",
                                      f"# {report_path.parent.name}", 1)
            content = content.replace("[results.json](results.json)",
                                      f"`{report_path.parent.name}/results.json` inside the evidence bundle")
            standalone += [content, ""]
        (staging / "performance-report.md").write_text("\n".join(standalone), encoding="utf-8")
        checksums = {path.relative_to(staging).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(staging.rglob("*")) if path.is_file()}
        save_json(staging / "publication.json", {"stage": "release", "release": release,
            "candidate": candidate, "source_run": run["html_url"], "run_attempt": run["run_attempt"],
            "created_at": datetime.now(timezone.utc).isoformat(), "sha256": checksums})
        staging.rename(output)
    return output


def package(directory):
    directory = Path(directory)
    archive = directory.with_name(directory.name + ".tar.gz")
    with archive.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as tar:
        tar.add(directory, arcname=directory.name)
    return archive
