"""A certificate-verified HTTP/2 test peer with controlled connection retirement."""

from contextlib import contextmanager
import socket
import socketserver
from threading import Event, Lock, Thread
import time

import h2.config
import h2.connection
import h2.events
import h2.exceptions
import h2.settings

from test.tls_certificate import tls_certificate


@contextmanager
def http2_peer(*, retire_first=False, idle_retirement=None,
               max_concurrent_streams=None, response_delay=0,
               settings_change_after=None, changed_stream_limit=None,
               payload=None, body_delay=0, body_chunk_size=16384,
               response=None, alpn_protocols=("h2",)):
    if body_chunk_size < 1 or body_delay < 0:
        raise ValueError("Body chunk size must be positive and delay nonnegative")
    with tls_certificate() as (certificate, context):
        context.set_alpn_protocols(list(alpn_protocols))

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
                        with self.server.lock:
                            self.server.negotiated_protocols.append(sock.selected_alpn_protocol())
                        sock.settimeout(0.01)
                        connection = h2.connection.H2Connection(
                            config=h2.config.H2Configuration(client_side=False))

                        def send_pending():
                            # The short read poll must not become the deadline
                            # for writing several concurrent large responses.
                            sock.settimeout(3)
                            try:
                                sock.sendall(connection.data_to_send())
                            finally:
                                sock.settimeout(0.01)

                        connection.initiate_connection()
                        if max_concurrent_streams is not None:
                            connection.update_settings({
                                h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: max_concurrent_streams})
                        send_pending()
                        last_stream = None
                        last_activity = time.monotonic()
                        retired = False
                        pending = {}
                        headers_by_stream = {}
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
                                    send_pending()
                                    retired = True
                                data = None
                            if data == b"":
                                with self.server.lock:
                                    self.server.errors.append(("EOF", f"connection={number} requests={requests}"))
                                return
                            if retired:
                                continue
                            for event in connection.receive_data(data) if data else []:
                                if isinstance(event, h2.events.RequestReceived):
                                    headers_by_stream[event.stream_id] = dict(event.headers)
                                    with self.server.lock:
                                        self.server.paths.append(dict(event.headers)[b":path"].decode())
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
                                    request_headers = headers_by_stream.pop(stream_id)
                                    if response is not None:
                                        status, headers, content = response(request_headers)
                                    else:
                                        total = 100 if payload is None else len(payload)
                                        start, end = 0, 0 if payload is None else total - 1
                                        if b"range" in request_headers:
                                            start, end = (int(part) for part in request_headers[b"range"]
                                                          .removeprefix(b"bytes=").split(b"-"))
                                        content = b"x" if payload is None else payload[start:end + 1]
                                        status = 206
                                        headers = [("content-length", str(len(content))),
                                                   ("content-range", f"bytes {start}-{end}/{total}")]
                                    if request_headers[b":method"] == b"HEAD":
                                        content = b""
                                    connection.send_headers(stream_id, [(":status", str(status)), *headers])
                                    bodies[stream_id] = (content, 0, time.monotonic() + body_delay)
                                    pending.pop(stream_id)
                            for stream_id, (content, offset, ready_at) in list(bodies.items()):
                                if ready_at <= time.monotonic():
                                    if not content:
                                        connection.end_stream(stream_id)
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
                            send_pending()
                except (OSError, h2.exceptions.ProtocolError) as exc:
                    with self.server.lock:
                        self.server.errors.append((type(exc).__name__, str(exc)))
                    return

        server = Server(("127.0.0.1", 0), Handler)
        server.lock = Lock()
        server.connections = 0
        server.server_port = server.server_address[1]
        server.paths = []
        server.negotiated_protocols = []
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
