"""Finalize one complete saved end-to-end run without executing downloaded code."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from benchmark.common import save_json
from benchmark.e2e import plan
from benchmark.report import collect, render, summarize


def validate_run(run, repository):
    if (run["repository"]["full_name"] != repository
            or run["path"] != ".github/workflows/benchmark.yml"
            or run["event"] != "workflow_dispatch"
            or run["status"] != "completed" or run["conclusion"] != "success"):
        raise ValueError("Select a successful manual benchmark workflow from this repository")


def validate_record(record, candidate, run):
    if not summarize(record)["valid"]:
        raise ValueError("Incomplete or invalid evidence cannot become a release report")
    if record["phases"] != plan.phases():
        raise ValueError("A complete twelve-phase workload is required")
    if record["plan"]["symbols"] != sorted(plan.SAMPLE_SYMBOLS):
        raise ValueError("The complete declared ticker sample is required")
    if record["rounds"] < 6 or record["rounds"] % 2:
        raise ValueError("Release evidence requires at least six balanced rounds")
    if record["experiment"]["environments"]["candidate"]["commit"] != candidate:
        raise ValueError("Release tag does not identify the measured candidate commit")
    workflow = record.get("workflow", {})
    if (workflow.get("repository") != run["repository"]["full_name"]
            or str(workflow.get("run_id")) != str(run["id"])
            or str(workflow.get("run_attempt")) != str(run["run_attempt"])
            or workflow.get("sha") != run["head_sha"]):
        raise ValueError("Evidence does not belong to the selected workflow attempt")


def harness_evidence(source, expected):
    roots = sorted(Path(source).glob("**/harness/benchmark"))
    if not roots or not expected:
        raise ValueError("Missing harness source evidence")
    verified = None
    for root in roots:
        files = {}
        for relative, digest in expected.items():
            relative_path = PurePosixPath(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative:
                raise ValueError("Invalid harness evidence path")
            path = root / relative
            if (not path.is_file() or path.is_symlink()
                    or not path.resolve().is_relative_to(root.resolve())):
                raise ValueError("Missing harness source evidence")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("Harness evidence checksum mismatch")
            files[relative] = content
        verified = files
    return verified


def finalize(source, output, release, candidate, run):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", release):
        raise ValueError("Release tag must be a simple filename-safe identifier")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("The release candidate must be a full Git commit")
    validate_run(run, run["repository"]["full_name"])
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError("Publication destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="benchmark-publication-") as temporary:
        staging = Path(temporary) / "bundle"
        target = collect(source, staging)
        record = json.loads(target.read_text())
        validate_record(record, candidate, run)
        files = harness_evidence(source, record["experiment"]["harness"])
        render(target, release=release)
        evidence_url = (f"https://github.com/{run['repository']['full_name']}/releases/download/"
                        f"{release}/performance-evidence.tar.gz")
        report = target.with_suffix(".md").read_text().replace(
            "[results.json](results.json)", "`results.json` inside the evidence bundle")
        (staging / "performance-report.md").write_text(
            f"# Performance report for {release}\n\nSource: {run['html_url']}.\n\n"
            f"[Complete evidence bundle]({evidence_url}).\n\n" + report, encoding="utf-8")
        # Preserve the original per-phase records as well as the merged report.
        for index, path in enumerate(sorted(source.rglob("results.json"))):
            raw = staging / "raw" / f"phase-{index:02d}.json"
            raw.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, raw)
        for relative, content in files.items():
            path = staging / "harness" / "benchmark" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for variant, environment in record["experiment"]["environments"].items():
            (staging / f"{variant}-dependencies.lock").write_text(environment["dependency_lock"], encoding="utf-8")
        (staging / "harness-dependencies.lock").write_text(
            record["experiment"]["harness_dependency_lock"], encoding="utf-8")
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
