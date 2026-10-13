"""Control valid HTTP/2 input frames around unchanged httpcore receive methods.

The synthetic network backend gates two reads. It isolates protocol scheduling,
not TCP, TLS, or CDN behavior. No product scheduling method is replaced.
"""

import asyncio
import argparse
from contextlib import asynccontextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import h2.config
import h2.connection
import httpcore
from httpcore._async.http2 import AsyncHTTP2Connection


async def until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("Controlled protocol state was not reached")
        await asyncio.sleep(0)


class GatedStream:
    def __init__(self, frames):
        self.frames = frames
        self.entered = [asyncio.Event() for _ in frames]
        self.release = [asyncio.Event() for _ in frames]
        self.reads = 0

    async def read(self, max_bytes, timeout=None):
        index = self.reads
        self.reads += 1
        if index >= len(self.frames):
            raise AssertionError("Unexpected extra socket read")
        self.entered[index].set()
        await self.release[index].wait()
        return self.frames[index]

    async def write(self, data, timeout=None):
        pass

    async def aclose(self):
        pass


@asynccontextmanager
async def ready_stream_scenario(order=(3, 5), timeline=None):
    if sorted(order) != [3, 5]:
        raise ValueError("Waiter order must contain streams 3 and 5 once each")
    peer = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
    connection = AsyncHTTP2Connection(httpcore.Origin(b"https", b"example.test", 443), None)
    protocol = connection._h2_state
    protocol.initiate_connection()
    peer.initiate_connection()
    peer.receive_data(protocol.data_to_send())
    protocol.receive_data(peer.data_to_send())
    peer.receive_data(protocol.data_to_send())
    for stream_id in (1, 3, 5):
        protocol.send_headers(stream_id, [(":method", "GET"), (":scheme", "https"),
            (":authority", "example.test"), (":path", f"/{stream_id}")], end_stream=True)
        connection._events[stream_id] = []
    peer.receive_data(protocol.data_to_send())
    for stream_id in (1, 3, 5):
        peer.send_headers(stream_id, [(":status", "200")])
    # Headers are already consumed; each coroutine now awaits its first body event.
    protocol.receive_data(peer.data_to_send())
    peer.send_data(5, b"ready", end_stream=True)
    peer.send_data(1, b"reader", end_stream=True)
    first = peer.data_to_send()
    peer.send_data(3, b"later", end_stream=True)
    stream = GatedStream([first, peer.data_to_send()])
    connection._network_stream = stream
    tasks = {}

    async def receive(stream_id):
        request = httpcore.Request("GET", f"https://example.test/{stream_id}")
        if timeline is None:
            return await connection._receive_stream_event(request, stream_id)
        with timeline.request("controlled", "GET", f"https://example.test/{stream_id}"):
            return await connection._receive_stream_event(request, stream_id)

    try:
        tasks[1] = asyncio.create_task(receive(1))
        await asyncio.wait_for(stream.entered[0].wait(), 3)
        for position, stream_id in enumerate(order, 1):
            tasks[stream_id] = asyncio.create_task(receive(stream_id))
            await until(lambda: connection._read_lock._anyio_lock.statistics().tasks_waiting == position)
        stream.release[0].set()
        await asyncio.wait_for(stream.entered[1].wait(), 3)
        if order[0] == 5:
            await asyncio.wait_for(asyncio.shield(tasks[5]), 3)
        yield connection, stream, tasks
    finally:
        for gate in stream.release:
            gate.set()
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


async def observe_case(order, hold_seconds, instrumented):
    from benchmark.diagnostics.http2_stream_timeline import StreamTimeline

    timeline = StreamTimeline() if instrumented else None
    zero = time.perf_counter_ns()
    now = timeline.now if timeline else lambda: time.perf_counter_ns() - zero
    result = {"order": list(order), "hold_seconds": hold_seconds, "instrumented": instrumented}
    with timeline.installed() if timeline else nullcontext():
        async with ready_stream_scenario(order=order, timeline=timeline) as (connection, stream, tasks):
            result.update(hold_started_ns=now(), ready_task_done_at_hold_start=tasks[5].done(),
                          ready_data_in_queue=any(type(event).__name__ == "DataReceived"
                                                  for event in connection._events[5]))
            tasks[5].add_done_callback(lambda task: result.update(ready_task_done_ns=now()))
            await asyncio.sleep(hold_seconds)
            result["ready_task_done_before_release"] = tasks[5].done()
            result["second_input_released_ns"] = now()
            stream.release[1].set()
            events = await asyncio.wait_for(asyncio.gather(*(tasks[i] for i in (1, 3, 5))), 3)
            await asyncio.sleep(0)
            result["payloads_valid"] = [event.data for event in events] == [b"reader", b"later", b"ready"]
    if timeline:
        result["timeline"] = timeline.artifact()
    return result


def run(args):
    if args.output.exists():
        raise FileExistsError("Probe output already exists")
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "methodology": {
                  "scope": "Valid HTTP/2 frames with a gated synthetic network backend; no TCP/TLS/CDN",
                  "product": "Existing httpcore receive methods, H2 parser and AnyIO lock are unchanged",
                  "control": "Reverse waiter order with identical input frames; run hooks off and on",
                  "timing": "Injected input delay proves causality, not production frequency or speedup",
              }, "sources": {}, "cases": []}
    for name in ("benchmark/diagnostics/http2_stream_probe.py", "benchmark/diagnostics/http2_stream_timeline.py",
                 "benchmark/diagnostics/cache_timeline.py", "benchmark/diagnostics/connection_timeline.py",
                 "defeatbeta_api/client/http_runtime.py", "defeatbeta_api/client/http_pool.py"):
        report["sources"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()

    async def capture():
        for hold in args.hold_seconds:
            for instrumented in (False, True):
                for order in ((3, 5), (5, 3)):
                    case = await observe_case(order, hold, instrumented)
                    if not case["payloads_valid"] or case["ready_task_done_before_release"] != (order[0] == 5):
                        raise AssertionError("Controlled stream scheduling changed")
                    report["cases"].append(case)
                    print(f"order={order} hold={hold:.3f} hooks={instrumented} "
                          f"ready_before_release={case['ready_task_done_before_release']}", flush=True)
    try:
        asyncio.run(capture())
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hold-seconds", type=float, nargs="+", default=[0.025, 0.1])
    args = parser.parse_args()
    if any(not 0 < seconds <= 1 for seconds in args.hold_seconds):
        parser.error("Input hold durations must be positive and at most one second")
    run(args)
