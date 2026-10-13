"""Opt-in cache pipeline diagnostics; installed only in an isolated process.

Intervals are nested, not additive. Async operation time includes network and
event-loop scheduling; it is not pure network time. Bridge endpoint intervals
include instrumentation overhead. Filesystems must be quiescent on entry/exit.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import functools
import hashlib
import sys
from threading import local
import time
from unittest.mock import patch

from benchmark.diagnostics.connection_timeline import Timeline


class _ObservedLock:
    def __init__(self, lock, timeline, phase):
        self.raw = lock
        self.timeline = timeline
        self.phase = phase
        self.local = local()

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def __enter__(self):
        start = self.timeline.now()
        result = self.raw.__enter__()
        acquired = self.timeline.now()
        self.timeline.event(self.phase + "_wait", start, acquired)
        if not hasattr(self.local, "held"):
            self.local.held = []
        self.local.held.append(acquired)
        return result

    def __exit__(self, *args):
        acquired = self.local.held.pop()
        try:
            return self.raw.__exit__(*args)
        finally:
            self.timeline.event(self.phase + "_held", acquired, self.timeline.now())


class CacheTimeline(Timeline):
    def __init__(self):
        super().__init__()
        self.task_context = ContextVar("cache_diagnostic_task", default=None)
        self.bridge_context = ContextVar("cache_diagnostic_bridge", default=None)
        self.tasks = []
        self.bridges = []

    def event(self, phase, start, end, **details):
        super().event(phase, start, end, task_id=self.task_context.get(),
                      bridge_id=self.bridge_context.get(), **details)

    @contextmanager
    def request(self, *args, **kwargs):
        with super().request(*args, **kwargs) as item:
            item["task_id"] = self.task_context.get()
            yield item

    def events_for(self, phase, *, task_only=False):
        with self.lock:
            return [event for event in self.events if event["phase"] == phase
                    and (not task_only or event["task_id"] is not None)]

    def artifact(self):
        """Preserve raw relative timestamps and safe IDs, never URLs or errors' text."""
        from benchmark.workloads.http_pool_mixed import distribution

        phases = sorted({event["phase"] for event in self.events})
        return {
            "methodology": {
                "clock": "perf_counter_ns, relative to one timeline origin",
                "spans": "Nested and overlapping; do not sum as exclusive wall time",
                "bridge": "Submission-to-start, awaited operation, completion-to-caller-return",
                "operation": "Includes protocol locks, network and event-loop scheduling",
                "cpu": "Task CPU is download-thread CPU only, excluding the I/O thread",
                "scope": "Task IDs identify downloads, not every query sharing their futures",
            },
            "tasks": self.tasks, "bridges": self.bridges,
            "queries": self.queries, "requests": self.requests, "events": self.events,
            "phases": {phase: distribution([event["duration_ns"] / 1e9
                       for event in self.events if event["phase"] == phase]) for phase in phases},
            "bridge_summary": {key: distribution([item[key] / 1e9 for item in self.bridges if key in item])
                               for key in ("submit_to_start_ns", "operation_ns", "complete_to_return_ns")},
        }

    @contextmanager
    def installed(self, *, filesystems=()):
        from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
        from defeatbeta_api.client.http_runtime import HTTPRuntime
        from httpcore._async.http2 import AsyncHTTP2Connection
        from httpcore._synchronization import AsyncLock

        original_call = HTTPRuntime.call
        original_sha256 = hashlib.sha256
        original_async_enter = AsyncLock.__aenter__

        @functools.wraps(original_async_enter)
        async def async_enter(lock):
            caller = sys._getframe(1)
            connection = caller.f_locals.get("self")
            request = self.request_context.get()
            phase = None
            if request is not None and isinstance(connection, AsyncHTTP2Connection):
                phase = next((f"transport.async_h2_{name}_lock_wait"
                              for name in ("read", "write", "init", "state")
                              if getattr(connection, f"_{name}_lock", None) is lock), None)
            stream_id = caller.f_locals.get("stream_id")
            del caller
            if phase is None:
                return await original_async_enter(lock)
            start = self.now()
            try:
                return await original_async_enter(lock)
            finally:
                self.event(phase, start, self.now(), connection_id=request.get("connection_id"),
                           stream_id=stream_id if isinstance(stream_id, int) else None)

        @functools.wraps(original_call)
        def call(runtime, coroutine):
            with self.lock:
                item = {"id": len(self.bridges) + 1, "task_id": self.task_context.get(),
                        "query_id": self.query_context.get(), "start_ns": self.now()}
                request = self.request_context.get()
                item["request_id"] = request["id"] if request else None
                self.bridges.append(item)

            async def observed():
                item["operation_start_ns"] = self.now()
                token = self.bridge_context.set(item["id"])
                try:
                    return await coroutine
                finally:
                    self.bridge_context.reset(token)
                    item["operation_end_ns"] = self.now()

            wrapped = observed()
            try:
                return original_call(runtime, wrapped)
            except BaseException as exc:
                item["error_type"] = type(exc).__name__
                # A rejected runtime closes the wrapper before it ever awaits
                # the original operation. Retain the original cleanup contract.
                if "operation_start_ns" not in item and wrapped.cr_frame is None:
                    coroutine.close()
                raise
            finally:
                item["end_ns"] = self.now()
                item["duration_ns"] = item["end_ns"] - item["start_ns"]
                if "operation_end_ns" in item:
                    item["submit_to_start_ns"] = item["operation_start_ns"] - item["start_ns"]
                    item["operation_ns"] = item["operation_end_ns"] - item["operation_start_ns"]
                    item["complete_to_return_ns"] = item["end_ns"] - item["operation_end_ns"]

        @functools.wraps(original_sha256)
        def sha256(*args, **kwargs):
            if self.task_context.get() is None:
                return original_sha256(*args, **kwargs)
            start = self.now()
            try:
                return original_sha256(*args, **kwargs)
            finally:
                self.event("cache.checksum", start, self.now())

        with super().installed(), ExitStack() as stack:
            # Capture the base diagnostic's submit hook so worker-queue spans
            # receive the task identity as well as the originating query ID.
            original_submit = ThreadPoolExecutor.submit

            @functools.wraps(original_submit)
            def submit(executor, function, *args, **kwargs):
                if getattr(function, "__name__", "") != "_fetch_block":
                    return original_submit(executor, function, *args, **kwargs)
                with self.lock:
                    task = {"id": len(self.tasks) + 1, "queued_ns": self.now(),
                            "query_id": self.query_context.get()}
                    self.tasks.append(task)
                if len(args) >= 4:
                    task.update(offset=args[2], length=args[3])

                @functools.wraps(function)
                def work(*work_args, **work_kwargs):
                    task["start_ns"] = self.now()
                    cpu = time.thread_time_ns()
                    try:
                        return function(*work_args, **work_kwargs)
                    except BaseException as exc:
                        task["error_type"] = type(exc).__name__
                        raise
                    finally:
                        task["thread_cpu_ns"] = time.thread_time_ns() - cpu
                        task["end_ns"] = self.now()
                        task["duration_ns"] = task["end_ns"] - task["start_ns"]

                token = self.task_context.set(task["id"])
                try:
                    return original_submit(executor, work, *args, **kwargs)
                except BaseException as exc:
                    task["submission_error_type"] = type(exc).__name__
                    raise
                finally:
                    self.task_context.reset(token)

            stack.enter_context(patch.object(ThreadPoolExecutor, "submit", submit))
            stack.enter_context(patch.object(HTTPRuntime, "call", call))
            stack.enter_context(patch.object(AsyncLock, "__aenter__", async_enter))
            stack.enter_context(patch.object(hashlib, "sha256", sha256))
            for name in ("_request_range", "_memory_get", "_memory_put", "_stored_version", "_cat_io"):
                stack.enter_context(self.wrap_span(DatasetCacheFileSystem, name, "cache." + name.lstrip("_")))
            for filesystem in filesystems:
                for name, phase in (("_generation_lock", "cache.generation_lock"),
                                    ("_guard", "cache.guard")):
                    stack.enter_context(patch.object(filesystem, name,
                        _ObservedLock(getattr(filesystem, name), self, phase)))
            yield self
