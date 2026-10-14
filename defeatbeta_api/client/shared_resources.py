"""Bounded process resources independent of query and Ticker lifetimes."""

import atexit
from collections import OrderedDict
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import os
import logging
import re
import socket
import sys
import time
from contextvars import ContextVar
from threading import RLock
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

import httpx

from defeatbeta_api.client.http_pool import ManagedHTTPTransport


MAX_NETWORK_IDENTITIES = 16
_NETWORK_LOCK = RLock()
_NETWORK_POOLS = OrderedDict()
_PRIVATE_REQUEST = ContextVar("defeatbeta_private_http", default=False)


class _PrivateRequestFilter(logging.Filter):
    def filter(self, record):
        if _PRIVATE_REQUEST.get():
            record.msg = re.sub(r"(https?://[^\s'\"?]+)\?[^\s'\"]*",
                                r"\1?<redacted>", record.getMessage())
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_PrivateRequestFilter())


def dataset_file_identity(version, url, footer_index):
    """Use the same immutable file identity for bytes, metadata, and resolution."""
    relative = urlsplit(url).path.partition("/data/")[2]
    hint = footer_index.get(relative) if isinstance(footer_index, dict) else None
    hint = hint if isinstance(hint, dict) else {}
    size = hint.get("file_size")
    footer_size = hint.get("footer_size")
    digest = hint.get("footer_sha256")
    return (version, url,
            size if type(size) is int and size > 0 else None,
            footer_size if type(footer_size) is int and footer_size > 0 else None,
            digest if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None)


def network_identity(url, proxy=None, trust_env=True):
    """Resolve routing before choosing a pool, including environment changes."""
    parts = urlsplit(url)
    if proxy is None and trust_env:
        proxies = getproxies()
        proxy = None if proxy_bypass(parts.hostname) else (
            proxies.get(parts.scheme) or proxies.get("all"))
    return (proxy or None, os.environ.get("SSL_CERT_FILE") if trust_env else None,
            os.environ.get("SSL_CERT_DIR") if trust_env else None)


@contextmanager
def network_client(identity):
    """Borrow a shared client; never evict a resource with an active borrower."""
    closing = []
    with _NETWORK_LOCK:
        resource = _NETWORK_POOLS.get(identity)
        if resource is None:
            victim = None
            if len(_NETWORK_POOLS) >= MAX_NETWORK_IDENTITIES:
                victim = next((key for key, item in _NETWORK_POOLS.items()
                               if not item["active"]), None)
                if victim is None:
                    raise httpx.PoolTimeout("All network identities are in use")
            proxy, cert_file, cert_dir = identity
            import ssl
            import certifi

            context = ssl.create_default_context(
                cafile=cert_file or (None if cert_dir else certifi.where()), capath=cert_dir)
            context.keylog_filename = None
            # This HTTPX pool is a connection factory, not the allocator.
            limits = httpx.Limits(max_connections=None,
                                  max_keepalive_connections=None,
                                  keepalive_expiry=None)
            transport = ManagedHTTPTransport(
                verify=context, http2=True, proxy=proxy, trust_env=False, limits=limits,
                socket_options=[(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)])
            resource = {"client": httpx.Client(transport=transport, trust_env=False,
                                               follow_redirects=False), "active": 0}
            if victim is not None:
                closing.append(_NETWORK_POOLS.pop(victim)["client"])
            _NETWORK_POOLS[identity] = resource
        resource["active"] += 1
        _NETWORK_POOLS.move_to_end(identity)
    try:
        _close_clients(closing)
        yield resource["client"]
    finally:
        with _NETWORK_LOCK:
            resource["active"] -= 1


class SharedHttpClient:
    """An owner's lightweight handle; closing it leaves shared pools intact."""

    def __init__(self, proxy=None, timeout=60, trust_env=True):
        self.proxy = proxy
        self.timeout = timeout
        self.trust_env = trust_env
        self.closed = False

    def request(self, method, url, **kwargs):
        if self.closed:
            raise RuntimeError("HTTP handle is closed")
        identity = network_identity(url, self.proxy, self.trust_env)
        with network_client(identity) as client:
            kwargs.setdefault("timeout", self.timeout)
            # Client.request() always reads the complete response before return.
            kwargs["extensions"] = {**(kwargs.get("extensions") or {}),
                                    "defeatbeta_buffer_response": True}
            token = _PRIVATE_REQUEST.set(True)
            try:
                return client.request(method, url, **kwargs)
            finally:
                _PRIVATE_REQUEST.reset(token)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def head(self, url, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def close(self):
        self.closed = True


def close_network_resources():
    """Close idle process pools; active requests finish on their existing pool."""
    with _NETWORK_LOCK:
        keys = [key for key, resource in _NETWORK_POOLS.items() if not resource["active"]]
        clients = [_NETWORK_POOLS.pop(key)["client"] for key in keys]
    _close_clients(clients)


def _close_clients(clients):
    first_error = None
    for client in clients:
        try:
            client.close()
        except BaseException as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


class SharedCache:
    """Bounded immutable values with per-key single-flight and retry after failure."""

    def __init__(self, max_bytes=32 * 1024 * 1024, max_entries=256):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.lock = RLock()
        self.values = OrderedDict()
        self.pending = {}
        self.bytes = 0

    def get_or_build(self, key, build, *, weight=lambda value: 1,
                     valid=lambda value: True, force_if=None):
        with self.lock:
            entry = self.values.get(key)
            if entry is not None and valid(entry[0]) and entry[0] != force_if:
                self.values.move_to_end(key)
                return entry[0]
            if entry is not None:
                self.values.pop(key)
                self.bytes -= entry[1]
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = self.pending[key] = Future()
        if not owner:
            return future.result()
        try:
            value = build()
            size = weight(value)
            with self.lock:
                if size <= self.max_bytes:
                    self.values[key] = (value, size)
                    self.bytes += size
                    while self.bytes > self.max_bytes or len(self.values) > self.max_entries:
                        _, (_, removed_size) = self.values.popitem(last=False)
                        self.bytes -= removed_size
                # Publish the value and retire its build atomically. A forced
                # refresh must never join a completed, invalidated generation.
                self.pending.pop(key, None)
            future.set_result(value)
            return value
        except BaseException as exc:
            with self.lock:
                if self.pending.get(key) is future:
                    self.pending.pop(key)
            future.set_exception(exc)
            raise

    def clear(self):
        with self.lock:
            if self.pending:
                raise RuntimeError("Cannot clear resources with pending work")
            self.values.clear()
            self.bytes = 0


def value_size(value):
    """Count owned Python containers and values once, including row overhead."""
    seen = set()

    def measure(item):
        identity = id(item)
        if identity in seen:
            return 0
        seen.add(identity)
        size = sys.getsizeof(item)
        if isinstance(item, dict):
            size += sum(measure(key) + measure(value) for key, value in item.items())
        elif isinstance(item, (tuple, list)):
            size += sum(measure(value) for value in item)
        return size

    return measure(value)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class ParquetIndex:
    rows: tuple

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)


FOOTERS = SharedCache()
PARQUET_INDEXES = SharedCache()
FILE_SIZES = SharedCache(max_entries=512)
RESOLVED_URLS = SharedCache(max_entries=512)
DATASET_SPECS = SharedCache(max_entries=32)


@contextmanager
def file_lock(path):
    """Wait for an OS-owned lock, released even when its owner process exits."""
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            # Windows permits locking beyond EOF. Avoid racing to initialize
            # an empty file, or modifying a byte another process has locked.
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    # LK_LOCK has an implicit ten-attempt cutoff. Match the
                    # blocking POSIX lock without treating contention as failure.
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _after_fork():
    # Inherited locks, in-flight futures and TLS streams belong to the parent.
    global _NETWORK_LOCK, _NETWORK_POOLS
    _NETWORK_LOCK = RLock()
    _NETWORK_POOLS = OrderedDict()
    for cache in (FOOTERS, PARQUET_INDEXES, FILE_SIZES, RESOLVED_URLS, DATASET_SPECS):
        cache.lock = RLock()
        cache.pending = {}
        cache.values = OrderedDict()
        cache.bytes = 0


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)
atexit.register(close_network_resources)
