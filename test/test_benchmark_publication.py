"""Reject incomplete publication and preserve every original phase record."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import publication
from benchmark.common import save_json
from test.test_benchmark import fake_record


class TestBenchmarkPublication(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.output = self.root / "source", self.root / "publication"
        self.run = {"id": 42, "run_attempt": 1, "head_sha": "c" * 40,
                    "repository": {"full_name": "owner/repo"}, "path": ".github/workflows/benchmark.yml",
                    "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
                    "html_url": "https://github.com/owner/repo/actions/runs/42"}
        self.record = fake_record()
        self.enterContext(patch.object(publication.plan, "SAMPLE_SYMBOLS", ("AAPL", "PDD")))
        content = b"raise RuntimeError('Evidence must never be executed')\n"
        self.record["experiment"]["harness"] = {"worker.py": hashlib.sha256(content).hexdigest()}
        self.source.mkdir()
        (self.source / "harness" / "benchmark").mkdir(parents=True)
        (self.source / "harness" / "benchmark" / "worker.py").write_bytes(content)
        self.path = self.source / "results.json"
        save_json(self.path, self.record)

    def finalize(self):
        return publication.finalize(self.source, self.output, "release-0.0.63", "b" * 40, self.run)

    def change(self, operation):
        value = deepcopy(self.record)
        operation(value)
        save_json(self.path, value)

    def test_preserves_raw_evidence_checksums_and_never_executes_harness(self):
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.finalize()
        self.assertEqual(hashlib.sha256((self.output / "raw" / "phase-00.json").read_bytes()).hexdigest(), digest)
        manifest = json.loads((self.output / "publication.json").read_text())
        for relative, expected in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), expected)
        self.assertIn("final release report", (self.output / "performance-report.md").read_text())
        self.assertEqual(publication.package(self.output).name, "publication.tar.gz")
        with self.assertRaises(FileExistsError):
            publication.package(self.output)
        with self.assertRaises(FileExistsError):
            self.finalize()

    def test_first_standalone_release_report_is_supported(self):
        self.record["experiment"]["environments"].pop("baseline")
        self.record["records"] = [s for s in self.record["records"] if s["variant"] == "candidate"]
        save_json(self.path, self.record)
        self.finalize()
        self.assertIn("standalone", (self.output / "performance-report.md").read_text())

    def test_missing_work_and_short_rounds_are_rejected(self):
        for change in (lambda r: r["records"].pop(), lambda r: r["phases"].pop(),
                       lambda r: r.update(rounds=2, records=[s for s in r["records"] if s["round"] <= 2])):
            self.change(change)
            with self.assertRaises(ValueError):
                self.finalize()
            self.assertFalse(self.output.exists())

    def test_wrong_candidate_and_workflow_attempt_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate commit"):
            publication.finalize(self.source, self.output, "v1", "d" * 40, self.run)
        self.change(lambda r: r["workflow"].update(run_attempt="2"))
        with self.assertRaisesRegex(ValueError, "workflow attempt"):
            self.finalize()

    def test_unsafe_release_and_changed_harness_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "filename-safe"):
            publication.finalize(self.source, self.output, "../release", "b" * 40, self.run)
        (self.source / "harness" / "benchmark" / "worker.py").write_text("# Modified\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.finalize()

    def test_failed_or_unrelated_run_is_rejected(self):
        for key, value in (("conclusion", "failure"), ("event", "pull_request"), ("path", "other.yml")):
            with self.assertRaises(ValueError):
                publication.validate_run({**self.run, key: value}, "owner/repo")
