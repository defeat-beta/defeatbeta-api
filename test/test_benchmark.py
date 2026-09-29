"""Contract tests for the executable performance benchmark."""

import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import io
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

    def test_data_cache_snapshot_excludes_prewarmed_footer_and_parquet_header(self):
        benchmark = load_benchmark_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "object.parquet-0-4.block").write_bytes(b"header")
            (root / "object-100-8.footer").write_bytes(b"footer")
            (root / "object-index.json").write_text("{}", encoding="utf-8")
            self.assertEqual(benchmark.data_cache_snapshot(root), {"files": 0, "bytes": 0})
            (root / "object-4-100.block").write_bytes(b"data")
            self.assertEqual(benchmark.data_cache_snapshot(root), {"files": 1, "bytes": 4})
            (root / "object.json-0-4.block").write_bytes(b"json")
            self.assertEqual(benchmark.data_cache_snapshot(root), {"files": 2, "bytes": 8})

    def test_run_parser_can_disable_footer_preload_for_empty_cache_control(self):
        benchmark = load_benchmark_module()
        self.assertEqual(benchmark.build_parser().parse_args(["run"]).cache_layout,
                         "extent")
        args = benchmark.build_parser().parse_args([
            "run", "--cache-layout", "io", "--no-cache-footer-preload",
        ])
        self.assertFalse(args.cache_footer_preload)

    def test_api_workload_rejects_hidden_metadata_before_cold_query(self):
        benchmark = load_benchmark_module()

        class FakeConfiguration:
            def __init__(self, **kwargs):
                self.directory = Path(kwargs["cache_directory"])

        class FakeDuckDBClient:
            connection = object()
            _dataset_fs = SimpleNamespace(metrics=lambda: {"downloaded_bytes": 256})

        class FakeTicker:
            def __init__(self, symbol, config, **kwargs):
                (config.directory / "object-100-8.footer").write_bytes(b"footer")
                (config.directory / "object-index.json").write_text("{}", encoding="utf-8")
                self.duckdb_client = FakeDuckDBClient()

            def price(self):
                return pd.DataFrame({"symbol": ["AAPL"]})

        @contextmanager
        def recorder(sink):
            yield

        api = benchmark.ApiBindings(FakeConfiguration, FakeTicker, recorder)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "cache was not empty"):
                benchmark.run_api_workload({
                    "symbol": "AAPL", "cache_directory": directory,
                    "configuration": {"cache_layout": "extent"},
                }, api=api, diagnostics=False)

    def test_report_displays_project_cache_transfer_metrics(self):
        report = load_report_module()
        description = report._cache_description({
            "cache_after_query": {"files": 4, "bytes": 2_967_427},
            "cache_metrics": {"range_requests": 3, "downloaded_bytes": 2_967_312},
        })
        self.assertIn("3 ranges", description)
        self.assertIn("downloaded", description)

    def test_report_breakdown_exposes_query_time_parquet_metadata_preparation(self):
        report = load_report_module()
        breakdown = report._breakdown({
            "primary_metric": "execute_query_seconds",
            "samples": [{
                "status": "ok", "execute_query_seconds": 2.0,
                "performance": {
                    "duckdb.prepare_parquet_metadata": {"seconds": 0.75, "calls": 1},
                    "duckdb.prefetch_ranges": {"seconds": 0.05, "calls": 1},
                },
            }],
        })
        self.assertEqual(breakdown["metadata_prepare"], 0.75)
        self.assertEqual(breakdown["range_prefetch"], 0.05)

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

    def test_transport_warmup_precedes_price_without_filling_disk_cache(self):
        benchmark = load_benchmark_module()
        calls = []

        class FakeConfiguration:
            def __init__(self, **kwargs):
                pass

        class FakeFileSystem:
            def __init__(self):
                self.downloaded = 0

            def prepare_connections(self, url, size):
                calls.append(("warm", url, size))
                self.downloaded = size

            def metrics(self):
                return {"downloaded_bytes": self.downloaded}

        class FakeTicker:
            def __init__(self, symbol, **kwargs):
                self.duckdb_client = SimpleNamespace(_dataset_fs=FakeFileSystem())

            def price(self):
                calls.append("price")
                return pd.DataFrame({"symbol": ["AAPL"]})

        class FakeRecorder:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        api = benchmark.ApiBindings(FakeConfiguration, FakeTicker,
                                    lambda sink: FakeRecorder())
        with tempfile.TemporaryDirectory() as directory:
            outcome = benchmark.run_api_workload({
                "symbol": "AAPL", "cache_directory": directory,
                "configuration": {}, "cache_connection_warmup_bytes": 256 * 1024,
            }, api=api, diagnostics=False)

        self.assertEqual(calls, [("warm", benchmark.STOCK_PRICES_URL, 256 * 1024),
                                 "price"])
        self.assertEqual(outcome["cache_before_query"], {"files": 0, "bytes": 0})
        self.assertEqual(outcome["cache_metrics_before_query"],
                         {"downloaded_bytes": 256 * 1024})
        self.assertEqual(outcome["cache_metrics_query_delta"],
                         {"downloaded_bytes": 0})
        self.assertGreaterEqual(outcome["connection_warmup_seconds"], 0)

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

    def test_cold_read_modes_cover_warmup_connections_and_chunk_sizes(self):
        benchmark = load_benchmark_module()
        modes = benchmark.cold_read_modes(1024 * 1024)

        self.assertEqual(len(modes), 16)
        self.assertIn((0, 3, 512 * 1024), modes)
        self.assertIn((1024 * 1024, 6, 256 * 1024), modes)
        self.assertEqual({mode[0] for mode in modes},
                         {0, 64 * 1024, 256 * 1024, 1024 * 1024})

    def test_cold_read_reassembles_exact_reference_bytes(self):
        benchmark = load_benchmark_module()
        reference = [b"abcd", b"ef"]
        plan = [("front_0_part_0", 0, 1), ("front_0_part_1", 2, 3),
                ("front_1_part_0", 4, 5)]
        transfers = [{"body": b"ab"}, {"body": b"cd"}, {"body": b"ef"}]

        self.assertEqual(
            benchmark.cold_read_payload_hash(plan, transfers),
            hashlib.sha256(b"abcdef").hexdigest(),
        )
        self.assertEqual(b"".join(reference), b"abcdef")
        with self.assertRaisesRegex(ValueError, "length"):
            benchmark.cold_read_payload_hash(plan, transfers[:-1])

    def test_cold_read_parser_accepts_proxy_and_local_output(self):
        benchmark = load_benchmark_module()
        args = benchmark.build_parser().parse_args([
            "network-cold-read", "--runs", "2", "--http-proxy",
            "http://127.0.0.1:8118", "--output", "/private/tmp/cold-read.json",
        ])

        self.assertEqual(args.runs, 2)
        self.assertEqual(args.http_proxy, "http://127.0.0.1:8118")
        self.assertEqual(str(args.output), "/private/tmp/cold-read.json")

    def test_connection_crossover_uses_disjoint_fresh_ranges(self):
        benchmark = load_benchmark_module()
        size = 466437904
        block = 1024 * 1024
        first = benchmark.connection_crossover_plan(size, block, 0, block, block // 2)
        second = benchmark.connection_crossover_plan(size, block, 1, block, block // 2)

        self.assertEqual(len(first["warmup"]), 6)
        self.assertEqual(len(first["query"]), 6)
        self.assertEqual(
            sum(end - start + 1 for _, start, end in first["query"]),
            sum(end - start + 1 for _, start, end in second["query"]),
        )
        first_intervals = [(start, end) for _, start, end in
                           first["warmup"] + first["query"]]
        second_intervals = [(start, end) for _, start, end in
                            second["warmup"] + second["query"]]
        self.assertTrue(all(left[1] < right[0] or right[1] < left[0]
                            for left in first_intervals for right in second_intervals))
        self.assertTrue(all(left[1] < right[0] or right[1] < left[0]
                            for left in first_intervals[:6]
                            for right in first_intervals[6:]))

    def test_connection_crossover_never_reuses_bytes_across_many_samples(self):
        benchmark = load_benchmark_module()
        ranges = []
        for index in range(24):
            plan = benchmark.connection_crossover_plan(
                466437904, 1024 * 1024, index, 1024 * 1024, 512 * 1024
            )
            ranges.extend((start, end) for _, start, end in
                          plan["warmup"] + plan["query"])
        ordered = sorted(ranges)
        self.assertTrue(all(left[1] < right[0]
                            for left, right in zip(ordered, ordered[1:])))

    def test_connection_crossover_heartbeat_uses_disjoint_bytes(self):
        benchmark = load_benchmark_module()
        plan = benchmark.connection_crossover_plan(
            466437904, 1024 * 1024, 22, 1, 512 * 1024,
            include_heartbeat=True,
        )

        self.assertEqual(len(plan["heartbeat"]), 6)
        ranges = sorted((start, end) for _, start, end in
                        plan["warmup"] + plan["heartbeat"] + plan["query"])
        self.assertTrue(all(left[1] < right[0]
                            for left, right in zip(ranges, ranges[1:])))

    def test_connection_crossover_verifies_socket_identity(self):
        benchmark = load_benchmark_module()
        warm_ports = list(range(50000, 50006))
        fresh_ports = list(range(51000, 51006))

        benchmark.validate_crossover_connections("same", warm_ports, warm_ports)
        benchmark.validate_crossover_connections("other", warm_ports, fresh_ports)
        benchmark.validate_crossover_connections("none", [], fresh_ports)
        with self.assertRaisesRegex(ValueError, "socket"):
            benchmark.validate_crossover_connections("other", warm_ports, warm_ports)
        with self.assertRaisesRegex(ValueError, "socket"):
            benchmark.validate_crossover_connections("same", warm_ports, fresh_ports)
        self.assertEqual(
            benchmark.crossover_connection_state("same", warm_ports, warm_ports),
            "reused",
        )
        self.assertEqual(
            benchmark.crossover_connection_state("same", warm_ports, fresh_ports),
            "replaced",
        )

    def test_connection_crossover_parser_accepts_warmup_size(self):
        benchmark = load_benchmark_module()
        args = benchmark.build_parser().parse_args([
            "network-crossover", "--runs", "3", "--warmup-bytes", "1048576",
            "--idle-seconds", "30", "--sample-offset", "9", "--modes", "same",
            "--heartbeat-at-seconds", "20",
            "--http-proxy", "http://127.0.0.1:8118",
        ])
        self.assertEqual(args.runs, 3)
        self.assertEqual(args.warmup_bytes, 1048576)
        self.assertEqual(args.idle_seconds, 30)
        self.assertEqual(args.sample_offset, 9)
        self.assertEqual(args.modes, ["same"])
        self.assertEqual(args.heartbeat_at_seconds, 20)

    def test_connection_crossover_heartbeat_reuses_warm_clients(self):
        benchmark = load_benchmark_module()
        calls = []
        sleeps = []

        class FakeClient:
            next_id = 0

            def __init__(self, **_kwargs):
                self.id = FakeClient.next_id
                FakeClient.next_id += 1

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, *_args, **_kwargs):
                return SimpleNamespace(
                    status_code=206,
                    headers={"Content-Range": "bytes 0-0/466437904"},
                    content=b"x",
                )

        async def fake_resolve(*_args):
            return "https://cdn.example/file"

        async def fake_probe(client, _url, name, start, end, _total,
                             _started_ns, include_body=False,
                             trace_transport=False):
            calls.append((client.id, name, start, end, include_body))
            length = end - start + 1
            result = {
                "name": name, "start": start, "end": end, "bytes": length,
                "http_version": "HTTP/2", "local_port": 50000 + client.id,
                "finish_seconds": 0.0,
            }
            if include_body:
                result["body"] = b"x" * length
            return result

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch.object(httpx, "AsyncClient", FakeClient), \
                patch.object(benchmark, "resolve_signed_url", fake_resolve), \
                patch.object(benchmark, "_probe_range", fake_probe), \
                patch.object(benchmark.asyncio, "sleep", fake_sleep):
            result = asyncio.run(benchmark.run_network_crossover_probe(
                "https://hf.example/file", None, 1, 60, 1024 * 1024,
                1, 512 * 1024, idle_seconds=65, sample_offset=22,
                modes=("same",), heartbeat_at_seconds=40,
            ))

        self.assertEqual(sleeps, [40, 25])
        self.assertEqual(len(calls), 18)
        self.assertEqual([item[0] for item in calls[:6]], list(range(1, 7)))
        self.assertEqual([item[0] for item in calls[6:12]], list(range(1, 7)))
        self.assertEqual([item[0] for item in calls[12:]], list(range(1, 7)))
        self.assertEqual(result["samples"][0]["heartbeat_bytes"], 6)
        self.assertEqual(result["samples"][0]["connection_state"], "reused")

    def test_network_crossover_reports_exception_type_for_empty_message(self):
        benchmark = load_benchmark_module()
        args = benchmark.build_parser().parse_args(["network-crossover"])
        stderr = io.StringIO()

        async def fail(*_args):
            raise TimeoutError()

        with patch.object(benchmark, "run_network_crossover_probe", fail), \
                patch("sys.stderr", stderr):
            status = benchmark.cmd_network_crossover(args)

        self.assertEqual(status, 1)
        self.assertIn("TimeoutError", stderr.getvalue())

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

    def test_network_transport_trace_records_names_without_sensitive_info(self):
        benchmark = load_benchmark_module()

        class FakeResponse:
            status_code = 206
            headers = {"Content-Range": "bytes 0-0/5"}
            http_version = "HTTP/2"
            extensions = {}

            def __init__(self, trace):
                self.trace = trace

            async def __aenter__(self):
                await self.trace("connection.connect_tcp.started", {"url": "secret"})
                await self.trace("connection.connect_tcp.complete", {"url": "secret"})
                await self.trace(
                    "http2.receive_response_headers.failed",
                    {"exception": ValueError("secret")},
                )
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def aiter_raw(self):
                yield b"a"

        class FakeClient:
            def stream(self, method, url, headers, extensions=None):
                return FakeResponse(extensions["trace"])

        result = asyncio.run(benchmark._probe_range(
            FakeClient(), "https://cdn.example/object?Signature=secret",
            "sample", 0, 0, 5, 0, trace_transport=True,
        ))

        self.assertEqual([event["name"] for event in result["transport_events"]], [
            "connection.connect_tcp.started", "connection.connect_tcp.complete",
            "http2.receive_response_headers.failed",
        ])
        self.assertEqual(
            result["transport_events"][-1]["error_type"], "ValueError"
        )
        self.assertNotIn("secret", str(result))

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
