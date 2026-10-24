"""Observe native range requests without retrying or excluding any request."""

from contextlib import contextmanager
import hashlib
from threading import Lock
import time
from unittest.mock import patch
from urllib.parse import urlsplit

from benchmark.common import redact_secrets


def exception_details(exc):
    details = {"error_type": type(exc).__name__, "error": redact_secrets(str(exc))}
    causes, seen = [], {id(exc)}
    cause = exc.__cause__ or exc.__context__
    while cause is not None and id(cause) not in seen and len(causes) < 8:
        seen.add(id(cause))
        causes.append({"error_type": type(cause).__name__, "error": redact_secrets(str(cause))})
        cause = cause.__cause__ or cause.__context__
    return {**details, "causes": causes}


class CachePreparationError(RuntimeError):
    def __init__(self, stage, exc, requests):
        self.evidence = {"stage": stage, **exception_details(exc), "requests": requests}
        super().__init__(f"{stage}: {type(exc).__name__}: {redact_secrets(str(exc))}")


@contextmanager
def observe_ranges():
    from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem

    original = DatasetCacheFileSystem._request_range
    state = {"request_count": 0, "events": [], "events_complete": True,
             "failed_requests": 0, "errors": []}
    lock = Lock()

    def request_range(filesystem, url, start, end, expected_total=None, *args, **kwargs):
        event = {"file": urlsplit(url).path.rsplit("/", 1)[-1],
                 "object_id": hashlib.sha256(url.encode()).hexdigest(),
                 "start": start, "end": end, "expected_total": expected_total,
                 "purpose": "connection_warmup" if kwargs.get("warmup") else
                            "size_probe" if expected_total is None and start == end == 0 else "data",
                 "status": "started"}
        with lock:
            state["request_count"] += 1
            if len(state["events"]) < 4096:
                state["events"].append(event)
            else:
                state["events_complete"] = False
        started = time.perf_counter()
        try:
            value = original(filesystem, url, start, end, expected_total, *args, **kwargs)
            event.update(status="ok", response_bytes=len(value[0]))
            return value
        except Exception as exc:
            event.update(status="error", **exception_details(exc))
            with lock:
                state["failed_requests"] += 1
                if len(state["errors"]) < 128:
                    state["errors"].append(event)
            raise
        finally:
            event["seconds"] = time.perf_counter() - started

    with patch.object(DatasetCacheFileSystem, "_request_range", request_range):
        yield state
