"""Require negotiated H2 for business traffic, including inside proxy tunnels."""

from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import ssl
from threading import Thread
import unittest
from unittest.mock import patch

import httpx

from defeatbeta_api.client.http_pool import (
    ConnectionManager, ConnectionPoolConfiguration, ManagedHTTPTransport, get_connection_pool_status,
)
from defeatbeta_api.client.shared_resources import SharedHttpClient, close_network_resources
from test.http2_peer import http2_peer
from test.proxy_peer import connect_proxy, socks_proxy
from test.tls_certificate import tls_certificate


@contextmanager
def non_h2_peer(protocols):
    with tls_certificate() as (certificate, context):
        context.set_alpn_protocols(protocols)

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                self.server.requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "1")
                self.end_headers()
                self.wfile.write(b"x")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server.requests = []
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://127.0.0.1:{server.server_port}/file", certificate, server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class TestHTTPProtocol(unittest.TestCase):
    def tearDown(self):
        close_network_resources()

    def test_plaintext_business_requests_are_rejected_before_connecting(self):
        client = SharedHttpClient(proxy="", timeout=1)
        with patch("defeatbeta_api.client.http_runtime.ConnectionFactory.create_connection",
                   side_effect=AssertionError("Plaintext request reached connection creation")) as create:
            with self.assertRaisesRegex(httpx.UnsupportedProtocol, "HTTP/2.*HTTPS"):
                client.get("http://127.0.0.1:1/file")
        create.assert_not_called()

    def test_missing_h2_is_rejected_without_business_requests_or_leaked_slots(self):
        for protocols in (["http/1.1"], []):
            for route in ("direct", "connect", "socks"):
                tunnel = {"direct": lambda: nullcontext(("", None)),
                          "connect": connect_proxy, "socks": socks_proxy}[route]
                with self.subTest(protocols=protocols, route=route), \
                        non_h2_peer(protocols) as (url, certificate, peer), \
                        patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}), \
                        tunnel() as (proxy, _):
                    client = SharedHttpClient(proxy=proxy, timeout=2)
                    for _ in range(2):
                        with self.assertRaisesRegex(httpx.UnsupportedProtocol, "HTTP/2.*ALPN"):
                            client.get(url)
                        state = get_connection_pool_status()
                        self.assertEqual(state["pending_requests"], 0)
                        self.assertEqual(state["connections"], [])
                    self.assertEqual(peer.requests, [])
                    client.close()
                    close_network_resources()
        with http2_peer() as (url, certificate, _), \
                patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            self.assertEqual(SharedHttpClient(proxy="").get(url).http_version, "HTTP/2")

    def test_only_h2_is_offered_even_when_peer_prefers_h1(self):
        for tunnel in (lambda: nullcontext(("", None)), connect_proxy, socks_proxy):
            with self.subTest(route=tunnel.__name__), \
                    http2_peer(alpn_protocols=("http/1.1", "h2")) as (url, certificate, peer), \
                    patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}), tunnel() as (proxy, _):
                client = SharedHttpClient(proxy=proxy, timeout=3)
                self.assertEqual(client.get(url).http_version, "HTTP/2")
                self.assertEqual(peer.negotiated_protocols, ["h2"])
                client.close()
                close_network_resources()

    def test_tls_proxy_may_use_h1_for_connect_while_business_uses_h2(self):
        with tls_certificate() as (proxy_certificate, proxy_context), \
                http2_peer() as (url, certificate, peer):
            proxy_context.set_alpn_protocols(["http/1.1"])
            with connect_proxy(tls_context=proxy_context) as (proxy_url, proxy):
                transport = ManagedHTTPTransport(
                    verify=ssl.create_default_context(cafile=str(certificate)),
                    proxy=httpx.Proxy(proxy_url, ssl_context=ssl.create_default_context(
                        cafile=str(proxy_certificate))), trust_env=False)
                with httpx.Client(transport=transport, timeout=3) as client:
                    for _ in range(2):
                        self.assertEqual(client.get(url).http_version, "HTTP/2")
                    self.assertEqual(proxy.tunnels, 1)
                    self.assertEqual(peer.connections, 1)

    def test_concurrent_negotiation_failures_release_waiters_and_capacity(self):
        manager = ConnectionManager(ConnectionPoolConfiguration(1, 1))
        with non_h2_peer([]) as (url, certificate, peer):
            transport = ManagedHTTPTransport(
                verify=ssl.create_default_context(cafile=str(certificate)),
                manager=manager, trust_env=False)
            with httpx.Client(transport=transport, timeout=5) as client, \
                    ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(client.get, url) for _ in range(16)]
                for future in futures:
                    with self.assertRaisesRegex(httpx.UnsupportedProtocol, "HTTP/2.*ALPN"):
                        future.result(timeout=10)
                self.assertEqual(peer.requests, [])
                self.assertEqual(manager.snapshot()["connections"], [])
                self.assertEqual(manager.snapshot()["pending_requests"], 0)

    def test_redirect_cannot_downgrade_to_plaintext_business_http(self):
        def redirect(_):
            return 302, [("location", "http://127.0.0.1:1/file"), ("content-length", "0")], b""

        with http2_peer(response=redirect) as (url, certificate, peer), \
                patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            client = SharedHttpClient(proxy="", timeout=3)
            with self.assertRaisesRegex(httpx.UnsupportedProtocol, "HTTP/2.*HTTPS"):
                client.get(url, follow_redirects=True)
            self.assertEqual(peer.paths, ["/file"])
            self.assertTrue(all(c["reserved_streams"] == 0
                                for c in get_connection_pool_status()["connections"]))
            client.close()
