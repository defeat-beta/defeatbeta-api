"""Exercise query materialization against real DuckDB without network access."""

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

import duckdb
from pandas.testing import assert_frame_equal

from test.client_stub import bare_client


class TestQueryMaterialization(unittest.TestCase):
    def setUp(self):
        self.client = bare_client()
        self.client.connection = duckdb.connect(config={"threads": 4})
        self.client.logger = logging.getLogger(__name__)
        self.addCleanup(self.client.connection.close)

    def assert_materialization_matches(self, sql):
        with self.client._get_cursor() as cursor:
            expected = cursor.sql(sql).df()
        actual = self.client._execute_query(sql)
        assert_frame_equal(actual, expected, check_exact=True)

    def test_scalar_nested_and_temporal_types(self):
        self.assert_materialization_matches("""
            SELECT 42::BIGINT AS integer_value, 1.25::DECIMAL(12, 2) AS decimal_value,
                   'text' AS text_value, true AS boolean_value, NULL::BIGINT AS null_value,
                   'NaN'::DOUBLE AS nan_value, 'Infinity'::DOUBLE AS infinity_value,
                   DATE '2026-10-20' AS date_value,
                   TIMESTAMP '2026-10-20 01:02:03' AS timestamp_value,
                   TIMESTAMPTZ '2026-10-20 01:02:03+00' AS zoned_value,
                   [1, 2, NULL] AS list_value, {'name': 'item', 'n': 2} AS struct_value
        """)

    def test_empty_cte_pivot_and_multiple_statements(self):
        for sql in (
            "SELECT 1::BIGINT AS n WHERE false",
            "WITH items AS (SELECT * FROM range(5)) SELECT sum(range) AS total FROM items",
            "PIVOT (VALUES ('A', 1), ('B', 2)) t(label, n) ON label USING sum(n)",
            "SELECT 1 AS n; SELECT 2 AS n",
        ):
            with self.subTest(sql=sql):
                self.assert_materialization_matches(sql)

    def test_parquet_scan_filter_and_aggregation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rows.parquet"
            self.client.connection.execute(
                "COPY (SELECT i, i % 3 AS category, md5(i::VARCHAR) AS payload "
                "FROM range(10000) t(i)) TO ? (FORMAT PARQUET, ROW_GROUP_SIZE 2048)",
                [str(path)],
            )
            escaped = str(path).replace("'", "''")
            self.assert_materialization_matches(
                f"SELECT category, count(*) AS n, sum(i) AS total FROM '{escaped}' "
                "WHERE i >= 100 GROUP BY category ORDER BY category"
            )

    def test_errors_close_cursor_and_leave_connection_usable(self):
        original_get_cursor = self.client._get_cursor
        opened = []

        @contextmanager
        def track_cursor():
            with original_get_cursor() as cursor:
                opened.append(cursor)
                yield cursor

        self.client._get_cursor = track_cursor
        for sql in (
            "SELEC 1", "SELECT missing_column FROM range(2)",
            "SELECT * FROM missing_table", "SELECT CAST(value AS INTEGER) FROM (VALUES ('bad')) t(value)",
        ):
            with self.subTest(sql=sql):
                with original_get_cursor() as cursor:
                    with self.assertRaises(duckdb.Error) as reference:
                        cursor.sql(sql).df()
                with self.assertRaises(type(reference.exception)):
                    self.client._execute_query(sql)
                with self.assertRaises(duckdb.ConnectionException):
                    opened[-1].execute("SELECT 1")
                self.assertEqual(self.client._execute_query("SELECT 42 AS n").iloc[0, 0], 42)
                with self.assertRaises(duckdb.ConnectionException):
                    opened[-1].execute("SELECT 1")

    def test_concurrent_queries_have_independent_results(self):
        barrier = Barrier(16)

        def query(index):
            barrier.wait(timeout=10)
            frame = self.client._execute_query(
                f"SELECT {index}::BIGINT AS caller, sum(i) AS total FROM range(10000) t(i)"
            )
            return int(frame.iloc[0, 0]), int(frame.iloc[0, 1])

        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(query, range(64)))
        self.assertEqual(results, [(i, 49995000) for i in range(64)])


if __name__ == "__main__":
    unittest.main()
