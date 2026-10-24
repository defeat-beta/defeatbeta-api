"""Protect version isolation helpers, result fingerprints and the fixed-data service."""

import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest

import httpx
import pandas as pd

from benchmark import benchmark, common
from benchmark.support import fixture
from benchmark.support.server import serve_fixture


class TestBenchmarkHelpers(unittest.TestCase):
    def test_source_identity_includes_runtime_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            product = root / "defeatbeta_api"
            product.mkdir()
            (product / "query.sql").write_text("SELECT 1", encoding="utf-8")
            before = common.source_hashes(root)
            (product / "query.sql").write_text("SELECT 2", encoding="utf-8")
            self.assertNotEqual(before, common.source_hashes(root))

    def test_paired_order_balances_each_worker_count(self):
        for index in range(12):
            self.assertEqual([benchmark.paired_order(n, index) for n in range(6)].count(
                ("baseline", "candidate")), 3)

    def test_hash_preserves_duplicate_rows_column_names_and_nested_values(self):
        a = pd.DataFrame({"symbol": ["A", "B", "B"], "body": [[{"a": 1}], [{"b": 2}], [{"b": 2}]]})
        self.assertEqual(common.result_fingerprint(a), common.result_fingerprint(a.iloc[::-1]))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.drop(index=2)))
        self.assertNotEqual(common.result_fingerprint(a), common.result_fingerprint(a.rename(columns={"body": "x"})))

    def test_harness_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worker.py").write_text("# Frozen harness\n")
            expected = benchmark.harness_hashes(root)
            benchmark.verify_harness(root, root, expected)
            (root / "worker.py").write_text("# Modified harness\n")
            with self.assertRaises(ValueError):
                benchmark.verify_harness(root, root, expected)

    def test_secret_redaction(self):
        value = common.redact_secrets({"proxy": "socks5://name:secret@localhost:100", "url": "https://cdn.test/file?secret=abc"})
        self.assertNotIn("name:secret", json.dumps(value))
        self.assertNotIn("secret=abc", json.dumps(value))


@unittest.skipUnless(os.environ.get("DEFEATBETA_RUN_BENCHMARK_TLS_TESTS") == "1",
                     "Set DEFEATBETA_RUN_BENCHMARK_TLS_TESTS=1 for fixture integration")
class TestBenchmarkTLS(unittest.TestCase):
    def test_fixture_integrity_h2_and_independent_price_reference(self):
        import duckdb

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = fixture.generate(root / "fixture")
            self.assertEqual(fixture.verify(root / "fixture"), identity)
            with duckdb.connect() as con:
                result = con.execute("SELECT count(*), min(close), max(close) FROM read_parquet(?) WHERE symbol='PDD'",
                    [str(root / "fixture" / "stock_prices.parquet")]).fetchone()
            self.assertEqual(result, (32768, 50.0, 59.99))
            with serve_fixture(root / "fixture", root) as server:
                context = ssl.create_default_context(cafile=server["certificate"])
                with httpx.Client(verify=context, trust_env=False, http2=True) as http:
                    response = http.get(server["url"] + "/data/stock_prices.parquet", headers={"Range": "bytes=0-3"})
                    self.assertEqual((response.status_code, response.content, response.http_version),
                                     (206, b"PAR1", "HTTP/2"))
                    self.assertEqual(http.get(server["url"] + "/data/stock_prices.parquet",
                                              headers={"Range": "bytes=8-4"}).status_code, 416)
            path = root / "fixture" / "stock_prices.parquet"
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                fixture.verify(root / "fixture")
