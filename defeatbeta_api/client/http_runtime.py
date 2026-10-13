"""Run the existing async HTTP/TLS stack on one process I/O thread.

The public download API remains synchronous. Protocol state and TLS objects
stay on one event loop, avoiding concurrent SSL calls and out-of-order HTTP/2
HEADERS in httpcore's synchronous implementation. No protocol is implemented
here: httpcore and its AnyIO backend still perform all network operations.
"""

import asyncio
import atexit
import inspect
import os
from threading import Lock, Thread, get_ident

import httpcore
import httpx


class HTTPRuntime:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._lock = Lock()
        self._closed = False
        self._thread = Thread(target=self._run, name="defeatbeta-http-io", daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            if tasks:
                self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()

    def call(self, coroutine):
        with self._lock:
            if self._closed or get_ident() == self._thread.ident:
                coroutine.close()
                raise RuntimeError("HTTP runtime is closed or called recursively from its I/O thread")
            future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result()
        except BaseException:
            future.cancel()
            raise

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._loop.call_soon_threadsafe(self._loop.stop)
        if get_ident() != self._thread.ident:
            self._thread.join(timeout=3)


_LOCK = Lock()
_RUNTIME = None


def _after_fork():
    global _LOCK, _RUNTIME
    _LOCK, _RUNTIME = Lock(), None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def runtime():
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is None:
            _RUNTIME = HTTPRuntime()
        return _RUNTIME


def _shutdown():
    if _RUNTIME is not None:
        _RUNTIME.close()


atexit.register(_shutdown)


class ResponseStream:
    def __init__(self, stream, io_runtime):
        self._stream = stream
        self._runtime = io_runtime

    def __iter__(self):
        iterator = self._stream.__aiter__()
        while True:
            try:
                yield self._runtime.call(anext(iterator))
            except StopAsyncIteration:
                return

    def close(self):
        self._runtime.call(self._stream.aclose())


class Connection:
    def __init__(self, raw):
        self._connection = raw
        self._runtime = runtime()

    async def _request(self, request):
        async def content():
            for chunk in request.stream:
                yield chunk

        original_trace = request.extensions.get("trace")
        extensions = dict(request.extensions)
        socket_options = extensions.pop("defeatbeta_socket_options", ())

        async def trace(event, info):
            if event.endswith(".connect_tcp.complete") and socket_options:
                stream = info["return_value"]
                sock = stream.get_extra_info("socket")
                if sock is not None:
                    try:
                        for option in socket_options:
                            sock.setsockopt(*option)
                    except BaseException:
                        try:
                            await stream.aclose()
                        except Exception:
                            pass
                        raise
            result = original_trace(event, info) if original_trace is not None else None
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("A synchronous HTTP client requires a synchronous trace callback")

        if original_trace is not None or socket_options:
            extensions["trace"] = trace
        routed = httpcore.Request(method=request.method, url=request.url, headers=request.headers,
                                  content=content(), extensions=extensions)
        response = await self._connection.handle_async_request(routed)
        response.stream = ResponseStream(response.stream, self._runtime)
        return response

    def handle_request(self, request):
        return self._runtime.call(self._request(request))

    def is_available(self):
        return self._connection.is_available()

    def is_closed(self):
        return self._connection.is_closed()

    def has_expired(self):
        return self._connection.has_expired()

    def close(self):
        self._runtime.call(self._connection.aclose())


class ConnectionFactory:
    def __init__(self, *args, **kwargs):
        self._pool = httpx.AsyncHTTPTransport(*args, **kwargs)._pool

    def create_connection(self, origin):
        return Connection(self._pool.create_connection(origin))

    def close(self):
        runtime().call(self._pool.aclose())
