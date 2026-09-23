"""Storage regression tests; run with python -m unittest test_records -v."""

import contextlib
from datetime import datetime, timedelta, timezone
from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch
import urllib.error

import bench
import queries
from records import (
    archive_comparison,
    archive_record,
    pack_reports,
    prune_local,
    unpack_comparison,
    unpack_reports,
    write_record,
)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        self.reports = [
            {"status": "complete", "environment": {"cpu": 10}, "samples": [{"result": {"rows": 1}}]},
            {"status": "complete", "environment": {"cpu": 10}, "samples": [{"result": {"rows": 2}}]},
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

    def comparison_reports(self, tag, suite_id, resolve_direct, environment=None,
                           settings=None, result_suffix=""):
        symbols = ["AAPL", "KDP"]
        reports = []
        for index, symbol in enumerate(symbols, 1):
            result = {"rows": index, "sha256": f"{symbol}{result_suffix}"}
            samples = [
                {"status": "ok", "e2e_seconds": float(index + trial), "result": result}
                for trial in range(2)
            ]
            reports.append({
                "run_id": f"{suite_id}_{index}",
                "suite_id": suite_id,
                "suite_symbols": symbols,
                "schedule": "round_robin",
                "tag": tag,
                "status": "complete",
                "symbol": symbol,
                "revision": "revision-1",
                "url": "https://huggingface.co/file.parquet",
                "sql": "SELECT * FROM 'https://huggingface.co/file.parquet' WHERE symbol = ?",
                "resolve_direct": resolve_direct,
                "requested_runs": 2,
                "timeout_seconds": 600.0,
                "environment": environment or {"duckdb": "1.5.3"},
                "configured_settings": settings or {"http_keep_alive": True},
                "methodology": {"cold": "Fresh process and empty cache"},
                "samples": samples,
                "statistics": {
                    "count": 2,
                    "median_seconds": index + 0.5,
                    "min_seconds": float(index),
                    "max_seconds": float(index + 1),
                    "std_seconds": 0.707,
                },
            })
        return reports

    def test_comparison_archive_round_trip(self):
        baseline = self.root / "local" / "baseline.json"
        candidate = self.root / "local" / "candidate.json"
        write_record(baseline, self.comparison_reports(
            "baseline", "20240101T000000.000000Z_baseline", False,
        ))
        write_record(candidate, self.comparison_reports(
            "candidate", "20240102T000000.000000Z_candidate", True,
        ))

        archived = archive_comparison(
            baseline, candidate, self.root, "001_example",
        )
        baseline_reports, candidate_reports = unpack_comparison(
            json.loads(archived.read_text(encoding="utf-8")),
        )

        self.assertFalse(baseline_reports[0]["resolve_direct"])
        self.assertTrue(candidate_reports[0]["resolve_direct"])
        self.assertEqual(len(list((self.root / "archive").glob("*.json"))), 1)

    def test_comparison_rejects_mismatched_results_and_settings(self):
        baseline = self.root / "local" / "baseline.json"
        candidate = self.root / "local" / "candidate.json"
        write_record(baseline, self.comparison_reports(
            "baseline", "20240101T000000.000000Z_baseline", False,
        ))
        write_record(candidate, self.comparison_reports(
            "candidate", "20240102T000000.000000Z_candidate", True,
            result_suffix="-different",
        ))
        with self.assertRaisesRegex(ValueError, "result hashes or symbols"):
            archive_comparison(baseline, candidate, self.root, "001_mismatch")

        write_record(candidate, self.comparison_reports(
            "candidate", "20240102T000000.000000Z_candidate", True,
            settings={"http_keep_alive": False},
        ))
        with self.assertRaisesRegex(ValueError, "undeclared setting differences"):
            archive_comparison(baseline, candidate, self.root, "001_settings")
        archive_comparison(
            baseline,
            candidate,
            self.root,
            "001_allowed",
            allowed_setting_differences=["http_keep_alive"],
        )

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

        invalid = self.root / "local" / "invalid.json"
        write_record(invalid, [{"status": "invalid"}])
        with self.assertRaises(ValueError):
            archive_record(invalid, self.root, "003_invalid")

    def test_archive_rejects_mixed_environments(self):
        source = self.root / "local" / "mixed.json"
        write_record(source, [
            {"status": "complete", "environment": {"duckdb": "1.5.3"}},
            {"status": "complete", "environment": {"duckdb": "1.4.3"}},
        ])

        with self.assertRaises(ValueError):
            archive_record(source, self.root, "004_mixed")

    def test_suite_and_archive_cli(self):
        calls = []

        def worker(payload, timeout):
            calls.append(payload["symbol"])
            return {"status": "ok", "e2e_seconds": 1.0,
                    "result": {"rows": 1, "sha256": payload["symbol"]}}

        # Local runs never publish reports. Run a baseline and a candidate.
        for tag, resolve_flag in (("baseline-test", []), ("candidate-test", ["--resolve-direct"])):
            args = [
                "bench.py", "run", "--runs", "2", "--output", str(self.root),
                "--tag", tag, *resolve_flag,
            ]
            with patch("sys.argv", args), patch.object(bench, "preflight", return_value=({}, {})), \
                    patch.object(bench, "run_worker", side_effect=worker), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bench.main(), 0)
        paths = list((self.root / "local").glob("*.json"))
        self.assertEqual(len(paths), 2)
        self.assertEqual(calls, ["AAPL", "KDP", "ZTS"] * 4)
        self.assertFalse((self.root / "summary.md").exists())
        self.assertFalse((self.root / "archive").exists())
        self.assertFalse(list((self.root / "local").glob("*.md")))

        baseline = next(path for path in paths if "_baseline-test_" in path.name)
        candidate = next(path for path in paths if "_candidate-test_" in path.name)
        baseline_reports = unpack_reports(json.loads(baseline.read_text()))
        candidate_reports = unpack_reports(json.loads(candidate.read_text()))
        for report in baseline_reports:
            report["suite_id"] = "20240101T030405.000000Z_baseline_fixed"
        for report in candidate_reports:
            report["suite_id"] = "20240102T030405.000000Z_candidate_fixed"
        write_record(baseline, baseline_reports)
        write_record(candidate, candidate_reports)

        # One explicit publication produces one JSON and one Markdown report.
        args = [
            "bench.py", "archive",
            "--baseline-source", str(baseline),
            "--candidate-source", str(candidate),
            "--name", "001_example",
            "--output", str(self.root),
        ]
        with patch("sys.argv", args), patch.object(bench, "preflight", side_effect=AssertionError), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bench.main(), 0)
        archive = self.root / "archive" / "001_example.json"
        report = archive.with_suffix(".md")
        self.assertTrue(archive.exists())
        self.assertEqual(len(list((self.root / "archive").glob("*.json"))), 1)
        self.assertEqual(len(list((self.root / "archive").glob("*.md"))), 1)
        self.assertEqual(json.loads(archive.read_text())["format_version"], 3)
        self.assertIn(
            "Raw paired results: [archive JSON](./001_example.json)",
            report.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "| Run dates | baseline 2024-01-01 / candidate 2024-01-02 |",
            report.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "complete signed URL",
            report.read_text(encoding="utf-8"),
        )
        self.assertIn("Baseline median", report.read_text(encoding="utf-8"))
        self.assertIn("Candidate median", report.read_text(encoding="utf-8"))


class ResolveTests(unittest.TestCase):
    def test_resolve_retries_a_transient_connection_failure(self):
        headers = Message()
        headers["Location"] = "https://us.aws.cdn.hf.co/file.parquet?Signature=secret"
        redirect = urllib.error.HTTPError(
            "https://huggingface.co/file.parquet", 302, "Found", headers, None,
        )
        opener = Mock()
        opener.open.side_effect = [urllib.error.URLError("temporary TLS EOF"), redirect]

        with patch("urllib.request.build_opener", return_value=opener), \
                patch.object(queries.time, "sleep"):
            location, elapsed = queries.resolve_cdn_url(
                "https://huggingface.co/file.parquet",
            )

        self.assertEqual(location, headers["Location"])
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(opener.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
