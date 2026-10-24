"""Real loopback CONNECT proxies for HTTP transport correctness tests."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import select
import socket
import socketserver
from threading import Lock, Thread


def relay(client, upstream):
    try:
        while True:
            readable, _, _ = select.select([client, upstream], [], [], 0.05)
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                destination = upstream if source is client else client
                destination.sendall(data)
    except OSError:
        return


@contextmanager
def connect_proxy(*, tls_context=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_CONNECT(self):
            host, port = self.path.rsplit(":", 1)
            with self.server.lock:
                self.server.tunnels += 1
            with socket.create_connection((host, int(port)), timeout=3) as upstream:
                self.send_response(200)
                self.end_headers()
                relay(self.connection, upstream)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.lock = Lock()
    server.tunnels = 0
    if tls_context is not None:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        scheme = "https" if tls_context is not None else "http"
        yield f"{scheme}://127.0.0.1:{server.server_port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@contextmanager
def socks_proxy():
    """A no-authentication SOCKS5 test tunnel for IPv4 and hostname targets."""
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(3)
            version, count = self.rfile.read(2)
            methods = self.rfile.read(count)
            if version != 5 or 0 not in methods:
                return
            self.wfile.write(b"\x05\x00")
            version, command, _, address_type = self.rfile.read(4)
            if version != 5 or command != 1:
                return
            if address_type == 1:
                host = socket.inet_ntoa(self.rfile.read(4))
            elif address_type == 3:
                host = self.rfile.read(self.rfile.read(1)[0]).decode()
            else:
                return
            port = int.from_bytes(self.rfile.read(2), "big")
            with socket.create_connection((host, port), timeout=3) as upstream:
                self.wfile.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
                with self.server.lock:
                    self.server.tunnels += 1
                relay(self.connection, upstream)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.lock = Lock()
    server.tunnels = 0
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"socks5://127.0.0.1:{server.server_address[1]}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
