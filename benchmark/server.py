"""Separate Hypercorn HTTPS fixture server; HTTP framing is owned by Hypercorn."""

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time


class RangeApplication:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.requests = self.bytes = self.ranges = 0
        self.protocols = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                await send({"type": event["type"] + ".complete"})
                if event["type"] == "lifespan.shutdown":
                    return
        if scope["type"] != "http":
            return
        path = scope["path"]
        headers, content, status = [], b"", 200
        if path == "/status":
            import psutil
            process = psutil.Process()
            cpu = process.cpu_times()
            content = json.dumps({"requests": self.requests, "bytes": self.bytes, "ranges": self.ranges,
                                  "protocols": self.protocols, "cpu_seconds": cpu.user + cpu.system,
                                  "rss_bytes": process.memory_info().rss}).encode()
        elif path.startswith("/resolve/"):
            filename = path.rsplit("/", 1)[-1]
            target = self.directory / filename
            if not target.is_file():
                status = 404
            else:
                host = dict(scope["headers"])[b"host"].decode().replace("127.0.0.1", "localhost")
                status = 302
                headers = [(b"location", f"https://{host}/data/{filename}".encode()),
                           (b"x-linked-size", str(target.stat().st_size).encode())]
        elif path == "/spec.json" or path.startswith("/data/"):
            filename = path.rsplit("/", 1)[-1]
            target = self.directory / filename
            if filename in ("", ".", "..") or not target.is_file():
                status = 404
            else:
                size = target.stat().st_size
                start, end = 0, size - 1
                value = dict(scope["headers"]).get(b"range")
                if value:
                    match = re.fullmatch(rb"bytes=(\d+)-(\d+)", value)
                    if match is None:
                        status = 416
                    else:
                        start, end = map(int, match.groups())
                        if not 0 <= start <= end < size:
                            status = 416
                        else:
                            status = 206
                            headers.append((b"content-range", f"bytes {start}-{end}/{size}".encode()))
                            self.ranges += 1
                if status != 416:
                    with target.open("rb") as stream:
                        stream.seek(start)
                        content = stream.read(end - start + 1)
        else:
            status = 404
        headers.append((b"content-length", str(len(content)).encode()))
        if path != "/status":
            self.requests += 1
            protocol = scope["http_version"]
            self.protocols[protocol] = self.protocols.get(protocol, 0) + 1
        await send({"type": "http.response.start", "status": status, "headers": headers})
        if scope["method"] != "HEAD":
            for offset in range(0, len(content), 65536):
                chunk = content[offset:offset + 65536]
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
                self.bytes += len(chunk)
        await send({"type": "http.response.body", "body": b"", "more_body": False})


@contextmanager
def serve_fixture(directory, runtime_directory):
    import httpx

    runtime_directory = Path(runtime_directory)
    certificate, key = runtime_directory / "certificate.pem", runtime_directory / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"],
                   check=True, capture_output=True, timeout=30)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"https://127.0.0.1:{port}"
    log = (runtime_directory / "server.log").open("w")
    process = subprocess.Popen([sys.executable, "-m", "benchmark.server", "--directory", str(directory),
                                "--port", str(port), "--certificate", str(certificate), "--key", str(key)], stdout=log, stderr=log)
    try:
        context = ssl.create_default_context(cafile=str(certificate))
        with httpx.Client(verify=context, trust_env=False, http1=False, http2=True, timeout=5) as client:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Fixture server exited; inspect server.log")
                try:
                    response = client.get(url + "/status")
                    response.raise_for_status()
                    break
                except httpx.RequestError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Fixture server did not start")
                    time.sleep(.05)
            expected = "HTTP/2"
            if response.http_version != expected:
                raise RuntimeError("Fixture protocol negotiation failed")
            yield {"url": url, "certificate": str(certificate), "protocol": expected,
                   "status": lambda: client.get(url + "/status").json()}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    config = Config()
    config.bind = [f"127.0.0.1:{args.port}"]
    config.certfile, config.keyfile = args.certificate, args.key
    config.alpn_protocols = ["h2"]
    config.keep_alive_timeout = 60
    config.keep_alive_max_requests = 100000
    asyncio.run(serve(RangeApplication(args.directory), config))
