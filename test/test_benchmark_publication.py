"""Publication contract: preserve evidence and reject incomplete or mixed runs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import publication, suite
from benchmark.common import save_json
from test.test_benchmark import fake_record


class TestBenchmarkPublication(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.output = self.root / "publication"
        self.commit = "b" * 40
        self.workflow = {"id": 42, "run_attempt": 1, "head_sha": "c" * 40,
                         "repository": {"full_name": "owner/repo"},
                         "path": ".github/workflows/benchmark.yml", "event": "workflow_dispatch",
                         "status": "completed", "conclusion": "success",
                         "html_url": "https://github.com/owner/repo/actions/runs/42"}
        # The publication tests exercise completeness against a small declared contract.
        # The suite tests independently verify the complete default-policy contract.
        self.plan = suite.make_suite("release")
        self.plan["cases"] = self.plan["cases"][:2]
        self.enterContext(patch.object(publication, "make_suite", return_value=self.plan))
        self.enterContext(patch("benchmark.report.ratio_interval", return_value=[.5, .5]))
        self.paths = []
        for index, (mode, protocol) in enumerate(sorted(publication.REQUIRED_EXPERIMENTS)):
            value = fake_record(mode)
            measurements = value["records"]
            value["records"] = []
            value["suite"] = deepcopy(self.plan)
            for case in self.plan["cases"]:
                for sample in measurements:
                    sample = deepcopy(sample)
                    sample["case"] = case["id"]
                    sample["measurement"]["results"][0]["task"] = case["tasks"][0]
                    value["records"].append(sample)
            value["resolved_suite_sha256"] = hashlib.sha256(json.dumps(value["suite"], sort_keys=True).encode()).hexdigest()
            value["workflow"] = {"run_id": "42", "run_attempt": "1", "sha": self.workflow["head_sha"],
                                 "repository": "owner/repo"}
            value["protocol_control"] = protocol
            value["fixture"] = {"files": {"fixture": "digest"}}
            for name, env in value["experiment"]["environments"].items():
                env.update(commit=self.commit if name == "candidate" else "a" * 40,
                           source_hashes={"source.py": "digest"}, dependency_lock="package==1\n")
            content = b"raise RuntimeError('Evidence must never be executed')\n"
            value["experiment"]["harness"] = {"worker.py": hashlib.sha256(content).hexdigest()}
            value["experiment"]["harness_dependency_lock"] = "harness==1\n"
            folder = self.source / f"artifact-{index}"
            (folder / "trial").mkdir(parents=True)
            harness = folder / "harness" / "benchmark"
            harness.mkdir(parents=True)
            (harness / "worker.py").write_bytes(content)
            path = folder / "trial" / "results.json"
            save_json(path, value)
            self.paths.append(path)

    def finalize(self):
        return publication.finalize(self.source, self.output, "release-0.0.63", self.commit, self.workflow)

    def change(self, change):
        value = json.loads(self.paths[0].read_text())
        change(value)
        save_json(self.paths[0], value)

    def test_finalization_preserves_all_raw_evidence_and_never_executes_it(self):
        expected = {hashlib.sha256(path.read_bytes()).hexdigest() for path in self.paths}
        self.finalize()
        actual = {hashlib.sha256(path.read_bytes()).hexdigest() for path in self.output.glob("*/results.json")}
        self.assertEqual(expected, actual)
        manifest = json.loads((self.output / "publication.json").read_text())
        for relative, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), digest)
        self.assertIn("final release report", (self.output / "README.md").read_text())
        for report in self.output.glob("*/results.md"):
            self.assertIn("release-0.0.63", report.read_text())
        self.assertTrue(publication.package(self.output).is_file())
        with self.assertRaises(FileExistsError):
            publication.package(self.output)
        with self.assertRaises(FileExistsError):
            self.finalize()

    def test_missing_experiment_is_rejected(self):
        for path in self.paths:
            with self.subTest(artifact=path.parent.parent.name):
                content = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, "Fixed-data and live-service"):
                        self.finalize()
                    self.assertFalse(self.output.exists())
                finally:
                    path.write_bytes(content)

    def test_contract_requires_fixed_data_and_live_service_without_h1(self):
        self.assertEqual(publication.REQUIRED_EXPERIMENTS,
                         {("controlled", "h2"), ("live", None)})

    def test_h1_evidence_cannot_replace_h2(self):
        self.change(lambda value: value.update(mode="controlled", protocol_control="http1"))
        with self.assertRaisesRegex(ValueError, "exactly one fixed-data H2"):
            self.finalize()
        self.assertFalse(self.output.exists())

    def test_archive_name_preserves_release_dots(self):
        folder = self.root / "release-0.0.63"
        folder.mkdir()
        self.assertEqual(publication.package(folder).name, "release-0.0.63.tar.gz")

    def test_missing_pair_is_rejected(self):
        self.change(lambda value: value["records"].pop())
        with self.assertRaisesRegex(ValueError, "invalid comparison"):
            self.finalize()

    def test_isolated_cache_evidence_cannot_be_published_as_default_behavior(self):
        self.change(lambda value: value["suite"].update(cache_policy="project-only"))
        with self.assertRaises(ValueError):
            self.finalize()

    def test_partial_suite_is_rejected_even_with_success_status(self):
        def remove_case(value):
            removed = value["suite"]["cases"].pop()["id"]
            value["records"] = [row for row in value["records"] if row["case"] != removed]
        self.change(remove_case)
        with self.assertRaisesRegex(ValueError, "complete standard release suite"):
            self.finalize()

    def test_wrong_candidate_or_workflow_attempt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate commit"):
            publication.finalize(self.source, self.output, "v1", "d" * 40, self.workflow)
        self.change(lambda value: value["workflow"].update(run_attempt="2"))
        with self.assertRaisesRegex(ValueError, "workflow attempt"):
            self.finalize()

    def test_short_run_cannot_be_promoted(self):
        def shorten(value):
            value["rounds"] = 2
            value["records"] = [row for row in value["records"] if row["round"] <= 2]
        self.change(shorten)
        with self.assertRaisesRegex(ValueError, "six balanced"):
            self.finalize()

    def test_dependency_mixture_is_rejected(self):
        self.change(lambda value: value["experiment"]["environments"]["baseline"].update(dependency_lock="changed==1\n"))
        with self.assertRaisesRegex(ValueError, "different sources, dependencies"):
            self.finalize()

    def test_unsafe_release_name_and_missing_harness_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "filename-safe"):
            publication.finalize(self.source, self.output, "../release", self.commit, self.workflow)
        for path in self.source.rglob("worker.py"):
            path.write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.finalize()

    def test_failed_or_unrelated_workflow_is_rejected(self):
        for field, value in (("conclusion", "failure"), ("event", "pull_request"), ("path", "other.yml")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                publication.validate_run({**self.workflow, field: value}, "owner/repo")
        with self.assertRaises(ValueError):
            publication.validate_run(self.workflow, "different/repository")
