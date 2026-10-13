# Direct and proxied CDN idle diagnostic

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

Run in a fresh process with the current environment proxy available:

```sh
.venv/bin/python -m benchmark.diagnostics.cdn_idle --output benchmark/results/local/cdn_idle.json
```

To repeat just the 90-second observation with a fresh connection in each profile:

```sh
.venv/bin/python -m benchmark.diagnostics.cdn_idle --idle-seconds 90 --output benchmark/results/local/cdn_idle_90.json
```

The diagnostic resolves one stock price file through the existing Hugging Face
client. It then reads the same 64 KiB range through six independent HTTPX
clients: direct and explicitly proxied access, each crossed with the following
controls:

- A 120-second local idle expiry, matching the production range client.
- No local idle expiry, to separate local eviction from remote/path failures.
- No local idle expiry plus TCP keepalive, with a 30-second probe idle period,
  10-second probe interval, and three probes where the OS supports those options.

Each profile has three connection slots, HTTP/2 enabled, and certificate
verification enabled. There is no HTTP heartbeat. Profiles start concurrently,
then send a real request after 30, 90, and 150 seconds without application
traffic. Actual per-client idle periods are recorded. TCP probes may still be
sent by the kernel in the enabled controls. All downloaded bytes stay in memory;
the production dataset cache and system proxy settings are not changed.

TCP options are applied to the observed response socket and read back. This is
intentional: passing socket options to a transport constructor does not prove
that a proxy connection received them. The diagnostic does not patch the
installed transport implementation to change its behavior.

## Interpretation

Compare protocol connection IDs, socket local ports, and HTTP/2 stream IDs.
A successful response does not by itself prove reuse: HTTPcore can reconnect
inside a send, and the diagnostic also permits one outer transport retry to
match the production range client's retry count. Both failed trace phases and
outer attempts are recorded. Response status, range, length, and SHA-256 must
agree before interpreting successful samples.

The additional HTTP/2 observation hook records GOAWAY error codes and last
stream IDs, and incoming PING/ACK event types. It passes the original event
objects back unchanged and omits opaque/debug payloads. Its timestamp is the
time HTTPcore read and decoded the frame, not the time the peer sent it. The
diagnostic sends no HTTP/2 PING itself.

`pool_before.local_idle_expired` records the local deadline before sending a
request. `available` is a cached protocol state, not a liveness probe; an idle
socket may already have been closed remotely without HTTPcore knowing it.
Socket peer addresses describe only the locally visible TCP connection. A
proxied sample does not reveal the proxy's CDN address or upstream TCP behavior.

The private HTTPcore observation hooks come from `connection_timeline.py` and
are confined to the diagnostic process. JSON records exclude signed URL query
strings, credentials, request/response headers, payloads, and exception messages.
OS socket options confirm configuration; packet capture would be required to
prove the exact timing and acknowledgement of every TCP probe.

This experiment measures idle reuse and reconnection cost on one current CDN
route. It does not establish a universal server timeout, maximum bandwidth, an
optimal connection pool size, or whether HTTP/2 PING would extend server idle
life. A direct-versus-proxy comparison may also involve different CDN backends.

The offline regression tests exercise socket reuse, local eviction, TCP option
readback, failed-connect observations, bounded transport retries, range
validation, and signed-query/exception-message redaction:

```sh
.venv/bin/python -m pytest test/test_cdn_idle.py test/test_connection_timeline.py -q
```
