"""Keep calibration bounded, resumable as evidence, and separate from release claims."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark.e2e import calibrate
from benchmark.common import save_json


class TestE2ECalibration(unittest.TestCase):
    def test_timeout_preserves_each_finished_latency_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def expired(command, **kwargs):
                response = Path(command[-1])
                response.with_suffix(".jsonl").write_text('{"id":"finished"}\n{"id":', encoding="utf-8")
                raise subprocess.TimeoutExpired(command, 1)

            with patch.object(calibrate.subprocess, "run", side_effect=expired):
                result = calibrate.run_worker(root, "latency.cold", {"action": "measure"}, 1)
            self.assertEqual(result["status"], "budget_exhausted")
            self.assertEqual(result["completed_tasks"], 1)
            self.assertEqual(result["results"], [{"id": "finished"}])

    def test_worker_failure_preserves_partial_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def failed(command, **kwargs):
                response = Path(command[-1])
                response.with_suffix(".jsonl").write_text('{"id":"finished"}\n', encoding="utf-8")
                save_json(response, {"status": "worker_error", "error": "Expected failure"})
                return subprocess.CompletedProcess(command, 1)

            with patch.object(calibrate.subprocess, "run", side_effect=failed):
                result = calibrate.run_worker(root, "latency.cold", {"action": "measure"}, 1)
            self.assertEqual(result["status"], "worker_error")
            self.assertEqual(result["completed_tasks"], 1)

    def test_incomplete_report_does_not_extrapolate_a_complete_matrix(self):
        record = {"commit": "a" * 40, "status": "budget_exhausted", "budget_seconds": 1,
                  "elapsed_seconds": 1.0, "phases": []}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibrate.render(record, root)
            content = (root / "calibration.md").read_text()
        self.assertIn("not a version comparison", content)
        self.assertNotIn("rough paired-run planning estimate", content)

    def test_dirty_checkout_is_rejected_before_any_queries(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(calibrate.subprocess, "check_output", side_effect=["a" * 40, " M benchmark/file.py"]), \
                patch.object(calibrate, "run_worker") as run:
            with self.assertRaisesRegex(ValueError, "Commit"):
                calibrate.calibrate(Path(directory) / "output", 1)
            run.assert_not_called()

    def test_invalid_budget_is_rejected_without_work(self):
        for budget in (0, -1, float("inf"), float("nan")):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                calibrate.calibrate(Path("/unused"), budget)
