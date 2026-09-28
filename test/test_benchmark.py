"""Contract tests for the executable performance benchmark."""

import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "benchmark" / "benchmark.py"
REPORT_PATH = ROOT / "benchmark" / "report.py"


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location("defeatbeta_benchmark", BENCHMARK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load benchmark module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_report_module():
    spec = importlib.util.spec_from_file_location("defeatbeta_benchmark_report", REPORT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load report module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkApiContractTests(unittest.TestCase):
    def test_cache_snapshot_excludes_version_and_lock_control_files(self):
        benchmark = load_benchmark_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".dataset-cache.lock").write_bytes(b"\0")
            (root / ".dataset-version.json").write_text(
                '{"version":"dataset-v1"}', encoding="utf-8"
            )
            (root / "sample.block").write_bytes(b"data")
            self.assertEqual(benchmark.cache_snapshot(root), {"files": 1, "bytes": 4})

    def test_report_displays_project_cache_transfer_metrics(self):
        report = load_report_module()
        description = report._cache_description({
            "cache_after_query": {"files": 4, "bytes": 2_967_427},
            "cache_metrics": {"range_requests": 3, "downloaded_bytes": 2_967_312},
        })
        self.assertIn("3 ranges", description)
        self.assertIn("downloaded", description)

    def test_run_parser_can_disable_project_cache(self):
        benchmark = load_benchmark_module()
        enabled = benchmark.build_parser().parse_args(["run"])
        disabled = benchmark.build_parser().parse_args(["run", "--no-cache"])
        self.assertTrue(enabled.cache)
        self.assertFalse(disabled.cache)

    def test_process_usage_has_windows_fallback(self):
        benchmark = load_benchmark_module()
        process = SimpleNamespace(
            cpu_times=lambda: SimpleNamespace(user=1.5, system=0.5),
            memory_info=lambda: SimpleNamespace(rss=123, peak_wset=456, pfaults=7),
        )
        with patch.object(benchmark, "resource", None), \
                patch("psutil.Process", return_value=process):
            usage = benchmark.process_usage()
        self.assertEqual((usage.ru_utime, usage.ru_stime), (1.5, 0.5))
        self.assertEqual(usage.ru_maxrss, 456)

    def test_httpx_transport_inherits_environment_only_without_explicit_proxy(self):
        benchmark = load_benchmark_module()

        self.assertEqual(
            benchmark.httpx_proxy_options(None),
            {"proxy": None, "trust_env": True},
        )
        self.assertEqual(
            benchmark.httpx_proxy_options("http://proxy.example:8123"),
            {"proxy": "http://proxy.example:8123", "trust_env": False},
        )

    def test_filesystem_trace_keeps_offsets_without_signed_url(self):
        benchmark = load_benchmark_module()
        event = benchmark.sanitize_filesystem_event({
            "timestamp": "2026-09-28 10:00:00+00:00",
            "fs": "HTTPFileSystem",
            "path": "https://us.aws.cdn.hf.co/object?Signature=secret",
            "op": "Read",
            "bytes": 1048576,
            "pos": 0,
        })

        self.assertEqual(event["host"], "us.aws.cdn.hf.co")
        self.assertEqual(event["bytes"], 1048576)
        self.assertEqual(event["pos"], 0)
        self.assertNotIn("secret", json.dumps(event))

    def test_trace_collects_io_from_query_cursor_without_extension_profile(self):
        benchmark = load_benchmark_module()
        query_cursor = object()
        captured = []

        @contextmanager
        def original_get_cursor():
            yield query_cursor

        with patch.object(benchmark, "collect_http_events", return_value=[]) as http:
            with patch.object(benchmark, "collect_filesystem_events", return_value=[]) as fs:
                with benchmark.trace_query_cursor(original_get_cursor, captured) as cursor:
                    self.assertIs(cursor, query_cursor)

        http.assert_called_once_with(query_cursor)
        fs.assert_called_once_with(query_cursor)
        self.assertEqual(captured[0]["http_events"], [])
        self.assertNotIn("cache_profile", captured[0])

    def test_http_trace_keeps_timing_and_range_without_signed_secrets(self):
        benchmark = load_benchmark_module()
        event = benchmark.sanitize_http_event({
            "request": {
                "type": "GET",
                "url": "https://us.aws.cdn.hf.co/object?Signature=secret",
                "start_time": "2026-09-28 10:00:00+00:00",
                "duration_ms": 1250,
                "headers": {"Range": "bytes=0-262143", "Authorization": "Bearer secret"},
            },
            "response": {
                "status": "PartialContent_206",
                "headers": {"Content-Range": "bytes 0-262143/466390118"},
            },
        })

        self.assertEqual(event["host"], "us.aws.cdn.hf.co")
        self.assertEqual(event["range"], "bytes=0-262143")
        self.assertEqual(event["duration_ms"], 1250)
        self.assertNotIn("secret", json.dumps(event))
        self.assertNotIn("Authorization", json.dumps(event))

    def test_api_run_parser_accepts_io_trace(self):
        benchmark = load_benchmark_module()

        args = benchmark.build_parser().parse_args(["run", "--trace-io"])

        self.assertTrue(args.trace_io)

    def test_api_run_parser_accepts_connection_cache_toggle(self):
        benchmark = load_benchmark_module()

        enabled = benchmark.build_parser().parse_args([
            "run", "--httpfs-connection-caching"
        ])
        disabled = benchmark.build_parser().parse_args([
            "run", "--no-httpfs-connection-caching"
        ])
        default = benchmark.build_parser().parse_args(["run"])

        self.assertTrue(enabled.httpfs_connection_caching)
        self.assertFalse(disabled.httpfs_connection_caching)
        self.assertIsNone(default.httpfs_connection_caching)

    def test_connection_cache_setting_precedes_measured_price_call(self):
        benchmark = load_benchmark_module()
        calls = []

        class FakeConnection:
            def execute(self, sql):
                calls.append(sql)

        class FakeDuckDBClient:
            connection = FakeConnection()

        class FakeConfiguration:
            def __init__(self, **kwargs):
                pass

        class FakeTicker:
            def __init__(self, symbol, **kwargs):
                self.duckdb_client = FakeDuckDBClient()

            def price(self):
                calls.append("price")
                return pd.DataFrame({"symbol": ["AAPL"]})

        class FakeRecorder:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        api = benchmark.ApiBindings(
            Configuration=FakeConfiguration,
            Ticker=FakeTicker,
            capture_performance=lambda sink: FakeRecorder(),
        )
        with tempfile.TemporaryDirectory() as directory:
            benchmark.run_api_workload({
                "symbol": "AAPL",
                "cache_directory": directory,
                "http_proxy": None,
                "configuration": {},
                "httpfs_connection_caching": True,
            }, api=api, diagnostics=False)

        self.assertEqual(calls, ["SET GLOBAL httpfs_connection_caching = true", "price"])

    def test_cold_query_uses_project_cache_metrics(self):
        benchmark = load_benchmark_module()
        calls = []

        class FakeRecorder:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class FakeConfiguration:
            def __init__(self, **kwargs):
                pass

        class FakeDuckDBClient:
            connection = object()
            _dataset_fs = SimpleNamespace(metrics=lambda: {"cache_misses": 1})

            def close(self):
                pass

        class FakeTicker:
            def __init__(self, symbol, **kwargs):
                self.duckdb_client = FakeDuckDBClient()

            def price(self):
                calls.append("price")
                return pd.DataFrame({"symbol": ["AAPL"]})

        def fake_frame_records(connection, sql):
            calls.append(sql)
            return []

        api = benchmark.ApiBindings(
            Configuration=FakeConfiguration,
            Ticker=FakeTicker,
            capture_performance=lambda sink: FakeRecorder(),
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(benchmark, "_frame_records", side_effect=fake_frame_records):
                with patch.object(benchmark, "_event_totals", return_value={
                    "duckdb.execute_query": {"seconds": 1.0, "calls": 1}
                }):
                    outcome = benchmark.run_api_workload({
                        "symbol": "AAPL",
                        "cache_directory": directory,
                        "http_proxy": None,
                        "configuration": {},
                    }, api=api)

        self.assertEqual(outcome["cache_metrics"], {"cache_misses": 1})
        self.assertFalse(any("cache_httpfs" in sql for sql in calls))

    def test_network_fanout_preserves_exact_query_bytes(self):
        benchmark = load_benchmark_module()
        reference = benchmark.network_range_plan(466390118, 1048576)

        for chunk_size, expected_count in ((1048576, 3), (524288, 6), (262144, 12)):
            with self.subTest(chunk_size=chunk_size):
                chunks = benchmark.network_fanout_plan(466390118, 1048576, chunk_size)
                self.assertEqual(len(chunks), expected_count)
                self.assertEqual(
                    [(start, end) for _, start, end in chunks],
                    [
                        (start, min(start + chunk_size - 1, end))
                        for _, original_start, end in reference
                        for start in range(original_start, end + 1, chunk_size)
                    ],
                )
                self.assertEqual(
                    sum(end - start + 1 for _, start, end in chunks), 2919526
                )
        with self.assertRaisesRegex(ValueError, "positive"):
            benchmark.network_fanout_plan(466390118, 1048576, 0)

    def test_network_fanout_schedule_rotates_modes(self):
        benchmark = load_benchmark_module()
        modes = [(1048576, 3), (524288, 3), (524288, 6)]

        self.assertEqual(benchmark.fanout_probe_schedule(2, modes), [
            (1, modes[0]), (1, modes[1]), (1, modes[2]),
            (2, modes[1]), (2, modes[2]), (2, modes[0]),
        ])

    def test_network_fanout_rejects_replaced_warm_connection(self):
        benchmark = load_benchmark_module()
        warm_ports = [51001, 51002, 51003]
        transfers = [
            {"http_version": "HTTP/2", "local_port": port}
            for port in warm_ports
        ]

        benchmark.validate_fanout_connections(transfers, warm_ports, [0, 1, 2])
        with self.assertRaisesRegex(ValueError, "warm connection"):
            benchmark.validate_fanout_connections(
                [dict(transfers[0], local_port=51004), *transfers[1:]],
                warm_ports,
                [0, 1, 2],
            )

    def test_network_range_probe_can_return_body_for_cross_mode_hash(self):
        benchmark = load_benchmark_module()

        class FakeResponse:
            status_code = 206
            headers = {"Content-Range": "bytes 0-2/5"}
            http_version = "HTTP/2"
            extensions = {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def aiter_raw(self):
                yield b"ab"
                yield b"c"

        class FakeClient:
            def stream(self, method, url, headers):
                return FakeResponse()

        result = asyncio.run(benchmark._probe_range(
            FakeClient(), "https://cdn.example/file", "sample", 0, 2, 5, 0,
            include_body=True,
        ))

        self.assertEqual(result["body"], b"abc")
        self.assertEqual(result["sha256"], hashlib.sha256(b"abc").hexdigest())

    def test_network_fanout_parser_accepts_runs_and_proxy(self):
        benchmark = load_benchmark_module()

        args = benchmark.build_parser().parse_args([
            "network-fanout", "--runs", "2", "--http-proxy", "http://127.0.0.1:8118"
        ])

        self.assertEqual(args.runs, 2)
        self.assertEqual(args.http_proxy, "http://127.0.0.1:8118")

    def test_network_transport_rotates_mode_order(self):
        benchmark = load_benchmark_module()

        self.assertEqual(benchmark.transport_probe_schedule(3), [
            (1, "http2_multiplexed"),
            (1, "http2_independent"),
            (1, "http1_independent"),
            (2, "http2_independent"),
            (2, "http1_independent"),
            (2, "http2_multiplexed"),
            (3, "http1_independent"),
            (3, "http2_multiplexed"),
            (3, "http2_independent"),
        ])
        with self.assertRaisesRegex(ValueError, "positive"):
            benchmark.transport_probe_schedule(0)
        self.assertEqual(
            [benchmark.transport_client_index(trial, 0, 3) for trial in (1, 2, 3)],
            [0, 1, 2],
        )

    def test_network_transport_requires_expected_protocol_and_connections(self):
        benchmark = load_benchmark_module()
        transfers = [
            {"http_version": "HTTP/2", "local_port": port}
            for port in (50001, 50002, 50003)
        ]

        benchmark.validate_transport_sample("http2_independent", transfers)
        with self.assertRaisesRegex(ValueError, "verifiable connections"):
            benchmark.validate_transport_sample(
                "http2_independent", [dict(item, local_port=50001) for item in transfers]
            )
        with self.assertRaisesRegex(ValueError, "HTTP/1.1"):
            benchmark.validate_transport_sample("http1_independent", transfers)
        benchmark.validate_transport_sample(
            "http2_multiplexed", [dict(item, local_port=50001) for item in transfers]
        )

    def test_network_transport_parser_accepts_runs_and_proxy(self):
        benchmark = load_benchmark_module()

        args = benchmark.build_parser().parse_args([
            "network-transport", "--runs", "3", "--http-proxy", "http://127.0.0.1:8118"
        ])

        self.assertEqual(args.runs, 3)
        self.assertEqual(args.http_proxy, "http://127.0.0.1:8118")

    def test_network_causality_parser_accepts_idle_duration(self):
        benchmark = load_benchmark_module()

        args = benchmark.build_parser().parse_args([
            "network-causality", "--idle-seconds", "30"
        ])

        self.assertEqual(args.idle_seconds, 30.0)

    def test_network_probe_resolves_without_importing_installed_api(self):
        benchmark = load_benchmark_module()

        class FakeResponse:
            status_code = 302
            headers = {"Location": "https://cdn.example/data.parquet?Signature=secret"}

        class FakeClient:
            async def head(self, url, **kwargs):
                self.url = url
                return FakeResponse()

        client = FakeClient()
        resolved = asyncio.run(benchmark.resolve_signed_url(
            client, "https://huggingface.co/file.parquet"
        ))

        self.assertEqual(client.url, "https://huggingface.co/file.parquet")
        self.assertEqual(resolved, FakeResponse.headers["Location"])

    def test_network_probe_range_plan_uses_distinct_cache_blocks(self):
        benchmark = load_benchmark_module()

        self.assertEqual(
            benchmark.network_range_plan(466278373, 1048576),
            [
                ("front_0", 0, 1048575),
                ("front_1", 1048576, 2097151),
                ("tail", 465567744, 466278372),
            ],
        )
        self.assertEqual(
            benchmark.network_range_plan(1048577, 1048576),
            [("front_0", 0, 1048575), ("front_1", 1048576, 1048576)],
        )
        self.assertEqual(
            benchmark.network_range_plan(2**60 + 1, 2**60)[1],
            ("front_1", 2**60, 2**60),
        )

    def test_causal_control_ranges_match_reference_transfer_lengths(self):
        benchmark = load_benchmark_module()
        reference = benchmark.network_range_plan(466278373, 1048576)
        control = benchmark.causal_control_plan(
            466278373, 1048576, 8, reference
        )

        self.assertEqual([end - start + 1 for _, start, end in control],
                         [end - start + 1 for _, start, end in reference])
        self.assertEqual(control[0][1], 8 * 1048576)
        with self.assertRaisesRegex(ValueError, "too small"):
            benchmark.causal_control_plan(1048577, 1048576, 8, reference)

    def test_network_probe_rejects_invalid_content_range(self):
        benchmark = load_benchmark_module()

        self.assertEqual(
            benchmark.parse_content_range("bytes 0-0/466278373"),
            (0, 0, 466278373),
        )
        for invalid in ("bytes */466278373", "bytes 1-0/10", "bytes 0-10/10"):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                benchmark.parse_content_range(invalid)

    def test_network_probe_validates_exact_range_and_length(self):
        benchmark = load_benchmark_module()
        benchmark.validate_range_response(
            206, "bytes 10-12/20", 3, 10, 12, 20, None
        )
        with self.assertRaisesRegex(ValueError, "Content-Range"):
            benchmark.validate_range_response(
                206, "bytes 9-12/20", 4, 10, 12, 20, None
            )
        with self.assertRaisesRegex(ValueError, "length"):
            benchmark.validate_range_response(
                206, "bytes 10-12/20", 2, 10, 12, 20, None
            )
        with self.assertRaisesRegex(ValueError, "encoding"):
            benchmark.validate_range_response(
                206, "bytes 10-12/20", 3, 10, 12, 20, "gzip"
            )

    def test_workload_calls_ticker_price(self):
        benchmark = load_benchmark_module()
        calls = []

        class FakeRecorder:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class FakeConfiguration:
            def __init__(self, **kwargs):
                calls.append(("configuration", kwargs))

        class FakeTicker:
            def __init__(self, symbol, **kwargs):
                calls.append(("ticker", symbol, kwargs))

            def price(self):
                calls.append(("price",))
                return FakeFrame()

        class FakeFrame:
            columns = ["symbol"]

            def __len__(self):
                return 1

        api = benchmark.ApiBindings(
            Configuration=FakeConfiguration,
            Ticker=FakeTicker,
            capture_performance=lambda sink: FakeRecorder(),
        )
        with tempfile.TemporaryDirectory() as directory:
            outcome = benchmark.run_api_workload(
                {
                    "symbol": "AAPL",
                    "cache_directory": directory,
                    "http_proxy": "http://127.0.0.1:8118",
                    "configuration": {},
                    "warm_repeats": 2,
                },
                api=api,
                diagnostics=False,
            )

        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(calls.count(("price",)), 3)
        self.assertEqual(len(outcome["warm_samples"]), 2)

    def test_primary_summary_uses_execute_query_time(self):
        benchmark = load_benchmark_module()
        samples = [
            {
                "status": "ok",
                "execute_query_seconds": float(index),
                "api_call_seconds": float(index + 100),
            }
            for index in range(1, 4)
        ]

        summary = benchmark.summarize(samples)

        self.assertEqual(summary["metric"], "execute_query_seconds")
        self.assertEqual(summary["median_seconds"], 2.0)
        self.assertIsNone(summary["p95_seconds"])

    def test_p95_requires_at_least_twenty_samples(self):
        benchmark = load_benchmark_module()
        samples = [
            {"status": "ok", "execute_query_seconds": float(index)}
            for index in range(1, 21)
        ]

        summary = benchmark.summarize(samples)

        self.assertAlmostEqual(summary["p95_seconds"], 19.05)

    def test_persisted_values_redact_urls_and_proxy_credentials(self):
        benchmark = load_benchmark_module()
        value = {
            "url": "https://cdn.example/file.parquet?Signature=secret&Expires=1",
            "proxy": "http://user:password@127.0.0.1:8118",
        }

        redacted = benchmark.redact_secrets(value)

        self.assertNotIn("secret", json.dumps(redacted))
        self.assertNotIn("password", json.dumps(redacted))
        self.assertIn("?<redacted>", redacted["url"])

    def test_worker_imports_the_repository_source_tree_first(self):
        benchmark = load_benchmark_module()

        environment = benchmark.worker_environment(
            {"http_proxy": None}, {"PYTHONPATH": "/existing/path"}
        )

        paths = environment["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(paths[0], str(ROOT))
        self.assertEqual(paths[1], "/existing/path")

class BenchmarkArchiveTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = load_benchmark_module()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def reports(self, tag, suite_id):
        reports = []
        for symbol in ("AAPL", "KDP"):
            result = {"rows": 1, "sha256": symbol}
            samples = [
                {
                    "status": "ok",
                    "execute_query_seconds": 1.0,
                    "api_call_seconds": 1.1,
                    "result": result,
                }
            ]
            reports.append({
                "status": "complete",
                "suite_id": suite_id,
                "suite_symbols": ["AAPL", "KDP"],
                "schedule": "round_robin",
                "tag": tag,
                "symbol": symbol,
                "revision": "main",
                "url": "https://huggingface.co/file.parquet",
                "api_call": "defeatbeta_api.data.ticker.Ticker.price",
                "resolve_direct": True,
                "primary_metric": "execute_query_seconds",
                "requested_runs": 1,
                "timeout_seconds": 600.0,
                "environment": {"duckdb": "1.5.3"},
                "implementation": {"duckdb_client.py": tag},
                "configured_settings": {"http_keep_alive": True},
                "methodology": {"cold": "Isolated local cache"},
                "samples": samples,
                "statistics": self.benchmark.summarize(samples),
            })
        return reports

    def test_archive_round_trip_allows_implementation_change(self):
        baseline = self.root / "baseline.json"
        candidate = self.root / "candidate.json"
        self.benchmark.write_record(
            baseline, self.reports("baseline", "20260923T000000.000000Z_baseline")
        )
        self.benchmark.write_record(
            candidate, self.reports("candidate", "20260923T010000.000000Z_candidate")
        )

        archived = self.benchmark.archive_comparison(
            baseline, candidate, self.root, "002_api_workload"
        )

        record = json.loads(archived.read_text(encoding="utf-8"))
        self.assertEqual(record["format_version"], 3)
        self.assertEqual(len(list((self.root / "archive").glob("*.json"))), 1)


class BenchmarkReportTests(unittest.TestCase):
    def test_existing_archives_still_render(self):
        report = load_report_module()
        sources = [
            ROOT / "benchmark" / "results" / "archive" / "000_baseline.json",
            ROOT / "benchmark" / "results" / "archive" / "001_resolve_once_cdn.json",
        ]
        with tempfile.TemporaryDirectory() as directory:
            for source in sources:
                destination = Path(directory) / f"{source.stem}.md"
                report.render_markdown(source, destination)
                rendered = destination.read_text(encoding="utf-8")
                self.assertIn("Stock Price Cold Query", rendered)
                self.assertIn("Result", rendered)


if __name__ == "__main__":
    unittest.main()
