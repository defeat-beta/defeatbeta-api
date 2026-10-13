"""A certificate-verified HTTP/2 test peer with controlled connection retirement."""

from contextlib import contextmanager
from pathlib import Path
import socket
import shutil
import socketserver
import ssl
import subprocess
import tempfile
from threading import Event, Lock, Thread
import time
import unittest

import h2.config
import h2.connection
import h2.events
import h2.exceptions
import h2.settings


@contextmanager
def http2_peer(*, retire_first=False, idle_retirement=None,
               max_concurrent_streams=None, response_delay=0,
               settings_change_after=None, changed_stream_limit=None,
               payload=None, body_delay=0, body_chunk_size=16384):
    if body_chunk_size < 1 or body_delay < 0:
        raise ValueError("Body chunk size must be positive and delay nonnegative")
    if shutil.which("openssl") is None:
        raise unittest.SkipTest("OpenSSL is required for the verified TLS fixture")
    with tempfile.TemporaryDirectory() as directory:
        certificate = Path(directory) / "certificate.pem"
        key = Path(directory) / "key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
        ], check=True, capture_output=True, timeout=15)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        context.set_alpn_protocols(["h2"])

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                with self.server.lock:
                    self.server.connections += 1
                    number = self.server.connections
                try:
                    with context.wrap_socket(self.request, server_side=True) as sock:
                        sock.settimeout(0.01)
                        connection = h2.connection.H2Connection(
                            config=h2.config.H2Configuration(client_side=False))
                        connection.initiate_connection()
                        if max_concurrent_streams is not None:
                            connection.update_settings({
                                h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: max_concurrent_streams})
                        sock.sendall(connection.data_to_send())
                        last_stream = None
                        last_activity = time.monotonic()
                        retired = False
                        pending = {}
                        ranges = {}
                        bodies = {}
                        requests = 0
                        settings_changed = False
                        while True:
                            try:
                                data = sock.recv(65536)
                            except socket.timeout:
                                if (idle_retirement and last_stream is not None and not retired
                                        and time.monotonic() - last_activity >= idle_retirement):
                                    connection.close_connection(error_code=0, last_stream_id=last_stream)
                                    sock.sendall(connection.data_to_send())
                                    retired = True
                                data = None
                            if data == b"":
                                with self.server.lock:
                                    self.server.errors.append(("EOF", f"connection={number} requests={requests}"))
                                return
                            if retired:
                                continue
                            for event in connection.receive_data(data) if data else []:
                                if isinstance(event, h2.events.RequestReceived) and payload is not None:
                                    headers = dict(event.headers)
                                    value = headers.get(b"range", f"bytes=0-{len(payload) - 1}".encode())
                                    start, end = (int(part) for part in value.removeprefix(b"bytes=").split(b"-"))
                                    ranges[event.stream_id] = (start, end)
                                if isinstance(event, h2.events.StreamEnded):
                                    last_activity = time.monotonic()
                                    last_stream = event.stream_id
                                    with self.server.lock:
                                        self.server.streams.append((number, event.stream_id))
                                        self.server.active_streams += 1
                                        self.server.peak_active_streams = max(
                                            self.server.peak_active_streams, self.server.active_streams)
                                    pending[event.stream_id] = time.monotonic() + response_delay
                                    requests += 1
                                    if (settings_change_after is not None and not settings_changed
                                            and requests >= settings_change_after):
                                        connection.update_settings({h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS:
                                                                    changed_stream_limit})
                                        settings_changed = True
                                        self.server.settings_changed.set()
                            for stream_id, ready_at in list(pending.items()):
                                if ready_at <= time.monotonic() and self.server.release_responses.is_set():
                                    start, end = ranges.pop(stream_id, (0, 0))
                                    content = b"x" if payload is None else payload[start:end + 1]
                                    total = 100 if payload is None else len(payload)
                                    connection.send_headers(stream_id, [
                                        (":status", "206"), ("content-length", str(len(content))),
                                        ("content-range", f"bytes {start}-{end}/{total}")])
                                    bodies[stream_id] = (content, 0, time.monotonic() + body_delay)
                                    pending.pop(stream_id)
                            for stream_id, (content, offset, ready_at) in list(bodies.items()):
                                if ready_at <= time.monotonic():
                                    while offset < len(content):
                                        size = min(body_chunk_size, connection.max_outbound_frame_size,
                                                   connection.local_flow_control_window(stream_id), len(content) - offset)
                                        if size <= 0:
                                            break
                                        end = offset + size
                                        connection.send_data(stream_id, content[offset:end], end_stream=end == len(content))
                                        offset = end
                                        if body_delay:
                                            break
                                    if offset < len(content):
                                        bodies[stream_id] = (content, offset, time.monotonic() + body_delay)
                                        continue
                                    bodies.pop(stream_id)
                                    with self.server.lock:
                                        self.server.active_streams -= 1
                                    if retire_first and number == 1:
                                        connection.close_connection(error_code=0,
                                                                    last_stream_id=stream_id)
                                        retired = True
                                        break
                            sock.sendall(connection.data_to_send())
                except (OSError, h2.exceptions.ProtocolError) as exc:
                    with self.server.lock:
                        self.server.errors.append((type(exc).__name__, str(exc)))
                    return

        server = Server(("127.0.0.1", 0), Handler)
        server.lock = Lock()
        server.connections = 0
        server.streams = []
        server.active_streams = 0
        server.peak_active_streams = 0
        server.release_responses = Event()
        server.release_responses.set()
        server.settings_changed = Event()
        server.errors = []
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://127.0.0.1:{server.server_address[1]}/file", certificate, server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
