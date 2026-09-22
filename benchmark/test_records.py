"""Storage regression tests; run with python -m unittest test_records -v."""

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bench
from records import archive_record, pack_reports, prune_local, unpack_reports, write_record


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        self.reports = [
            {"status": "complete", "environment": {"cpu": 10}, "samples": [{"result": {"rows": 1}}]},
            {"status": "invalid", "environment": {"cpu": 10}, "samples": [{"error": "network failure"}]},
        ]

    def record(self, age, tag="sample", status=None):
        created = self.now - timedelta(days=age)
        path = self.root / "local" / f"{created.strftime('%Y%m%dT%H%M%S.%fZ')}_{tag}.json"
        write_record(path, [{"status": status}] if status else self.reports)
        return path

    def test_lossless_deduplication(self):
        packed = pack_reports(self.reports)
        self.assertEqual(unpack_reports(packed), self.reports)
        self.assertEqual(packed["runs"][0]["environment"], packed["runs"][1]["environment"])

    def test_age_boundary_and_interrupted_runs(self):
        boundary = self.record(30)
        expired = self.record(31)
        stale = self.record(31, "interrupted", "running")
        active = self.record(0, "active", "running")
        unrelated = self.root / "local" / "unrelated.json"
        unrelated.write_text("{}")
        prune_local(self.root, now=self.now)
        self.assertTrue(boundary.exists())
        self.assertFalse(expired.exists())
        self.assertFalse(stale.exists())
        self.assertTrue(active.exists())
        self.assertTrue(unrelated.exists())

    def test_count_limit_and_archive_protection(self):
        paths = [self.record(index / 100, f"run{index}") for index in range(101)]
        archived = archive_record(paths[-1], self.root, "000_baseline")
        prune_local(self.root, now=self.now)
        self.assertEqual(len(list((self.root / "local").glob("*.json"))), 100)
        self.assertFalse(paths[-1].exists())
        self.assertTrue(archived.exists())
        self.assertEqual(unpack_reports(json.loads(archived.read_text())), self.reports)

    def test_archive_rejects_overwrite_traversal_and_unfinished_runs(self):
        source = self.record(0)
        archive_record(source, self.root, "001_example")
        with self.assertRaises(FileExistsError):
            archive_record(source, self.root, "001_example")
        with self.assertRaises(ValueError):
            archive_record(source, self.root, "../escape")
        with self.assertRaises(ValueError):
            archive_record(self.record(0, "active", "running"), self.root, "002_active")

    def test_suite_and_archive_cli(self):
        calls = []

        def worker(payload, timeout):
            calls.append(payload["symbol"])
            return {"status": "ok", "e2e_seconds": 1.0,
                    "result": {"rows": 1, "sha256": payload["symbol"]}}

        # Test run subcommand
        args = ["bench.py", "run", "--runs", "2", "--output", str(self.root), "--tag", "test"]
        with patch("sys.argv", args), patch.object(bench, "preflight", return_value=({}, {})), \
                patch.object(bench, "run_worker", side_effect=worker), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bench.main(), 0)
        paths = list((self.root / "local").glob("*.json"))
        self.assertEqual(len(paths), 1)
        reports = unpack_reports(json.loads(paths[0].read_text()))
        self.assertEqual(len(reports), 3)
        self.assertTrue(all(report["statistics"]["count"] == 2 for report in reports))
        self.assertEqual(calls, ["AAPL", "KDP", "ZTS"] * 2)
        self.assertFalse((self.root / "summary.md").exists())

        # Test archive subcommand
        args = ["bench.py", "archive", "--tag", "test", "--name", "001_example", "--output", str(self.root)]
        with patch("sys.argv", args), patch.object(bench, "preflight", side_effect=AssertionError), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bench.main(), 0)
        self.assertTrue((self.root / "archive" / "001_example.json").exists())


if __name__ == "__main__":
    unittest.main()
