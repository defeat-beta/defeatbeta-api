# CDN connection lifetime under regular HTTP traffic

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

Run in a fresh process with network access:

```sh
.venv/bin/python -m benchmark.diagnostics.cdn_active --output benchmark/results/local/cdn_active_10min.json
```

The diagnostic resolves the current stock-price CDN URL using the existing Hub
resolver, then uses a direct, certificate-verified HTTPX client for data requests.
The data transport ignores environment proxies and allows one connection with
one retained slot and no local idle expiry. TLS key logging is disabled.

It sends one `Range: bytes=0-0` GET initially and 60 more at ten-second deadlines
after the first completed response. Scheduling uses a monotonic clock. Actual
request durations and idle gaps are recorded; there is no background request,
HTTP/2 PING, custom heartbeat or change to TCP socket options. OS probe traffic
is not captured by this diagnostic. No local file cache serves the range.

Response status, Content-Range, byte count, content encoding and payload hash
are checked. The payload itself, signed URL query, response headers and exception
messages are not stored. The existing Timeline and HTTP/2 control-event hooks
observe requests without replacing the protocol stack's connection management.

There is no outer retry. HTTPcore can internally reassign a request, so the
report retains every observed protocol attempt as well as each final response's
connection ID, local port, peer, stream ID, and TCP/TLS handshake events. A
successful GET alone is not evidence of continuous physical connection reuse.

The report is saved after every sample. `same_connection_throughout` requires
valid HTTP/2 responses on one fully observed socket identity, a single protocol
connection ID across attempts, increasing stream IDs, one TCP connect, one TLS
handshake, matching payload hashes, and no decoded GOAWAY. Inspect status and
observed duration separately: a running partial report cannot establish the
full ten-minute bound. Frame timestamps represent client decoding, not the
unobserved server send time.

Survival establishes a lower bound for this request pattern and observed route.
It does not establish a maximum lifetime, prove a particular CDN timeout policy,
or justify adding automated keepalive requests to the product. A different DNS
answer from earlier idle experiments is recorded and limits direct comparison.

Validation:

```sh
.venv/bin/python -m pytest test/test_cdn_active.py -q
```

Tests cover range validation, absence of outer retries, error-message redaction,
and rejection of replacement sockets, missing identity, extra handshakes or
GOAWAY as evidence of uninterrupted reuse. Other relevant cases include HTTP/1.1
negotiation, server errors or ignored Range, signature expiry, network changes,
and a process suspension that causes a much larger actual idle gap. Those cases
must be identified in the report rather than presented as a clean survival run.
