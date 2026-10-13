"""Measure HTTP/1.1 fallback queueing under bounded shared pool capacities."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import statistics
from threading import Lock, Thread
import time

from defeatbeta_api.client import shared_resources
from defeatbeta_api.client.http_pool import configure_connection_pool, get_connection_pool_status


def run(output):
    if output.exists():
        raise FileExistsError("Benchmark output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            with self.server.lock:
                self.server.ports.add(self.client_address[1])
                self.server.active += 1
                self.server.peak = max(self.server.peak, self.server.active)
            time.sleep(0.02)
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.send_response(200)
            self.send_header("Content-Length", "1")
            self.end_headers()
            self.wfile.write(b"x")
            self.wfile.flush()
            with self.server.lock:
                self.server.active -= 1

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 128

    server = Server(("127.0.0.1", 0), Handler)
    server.lock = Lock()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = get_connection_pool_status()["configuration"]
    report = {"status": "running", "methodology": {
        "protocol": "Real loopback HTTP/1.1, one byte and 20 ms simulated service time",
        "scope": "Connection capacity and queueing control; not internet throughput",
        "requests": "64 requests per batch; fresh pool per capacity/concurrency pair",
    }, "cases": []}
    try:
        url = f"http://127.0.0.1:{server.server_port}/file"
        for capacity in (1, 4, 8, 16, 32):
            for concurrency in (1, 2, 4, 8, 16, 32):
                shared_resources.close_network_resources()
                configure_connection_pool(core_connections_per_origin=1,
                                          max_connections_for_all_origins=capacity)
                server.ports, server.active, server.peak = set(), 0, 0
                client = shared_resources.SharedHttpClient(proxy="", timeout=5)

                def query(_):
                    started = time.monotonic()
                    response = client.get(url)
                    assert response.content == b"x"
                    return time.monotonic() - started

                began = time.monotonic()
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    durations = sorted(executor.map(query, range(64)))
                case = {"capacity": capacity, "concurrency": concurrency,
                        "wall_seconds": time.monotonic() - began,
                        "median_seconds": statistics.median(durations),
                        "p95_seconds": durations[60], "connections": len(server.ports),
                        "peak_active": server.peak}
                report["cases"].append(case)
                output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
                print(f"capacity={capacity} concurrency={concurrency} "
                      f"seconds={case['wall_seconds']:.3f} connections={case['connections']}", flush=True)
        report["status"] = "complete"
    finally:
        shared_resources.close_network_resources()
        configure_connection_pool(**original)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
