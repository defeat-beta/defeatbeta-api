# OS TCP keepalive packet diagnostic

> Historical engineering report. Results and implementation details refer to
> the investigation recorded here. See the [report index](README.md) for
> current status and the [connection pool guide](../../doc/api/HTTP_Connection_Pool.md)
> for current behavior.

Run on this Mac in a fresh terminal process:

```sh
.venv/bin/python -m benchmark.diagnostics.tcp_keepalive_capture --output benchmark/results/local/tcp_keepalive_packets
```

The diagnostic requests an administrator password with `getpass`. The password
is sent to sudo through its stdin only and is not included in a command argument,
environment variable, source file, packet report, or capture log.

Two IPv4 source sockets are reserved before tcpdump starts. The capture filter
contains only those two source ports, the resolved CDN IPv4 address, and TCP
port 443. tcpdump captures on the route's actual interface without promiscuous
mode, requests 128 bytes per packet, caps the packet count at 2000, and has a
120-second alarm. Snapshot length and kernel packet drops are read back from
the capture log; unmet limits are reported explicitly.
After opening the capture device it drops privileges to the current user.

The diagnostic makes one 64 KiB range request per socket. One HTTPX transport
explicitly disables TCP keepalive; the other passes enabled/30-second idle/
10-second interval/three-probe settings through the transport's `socket_options`.
The actual response sockets are read back without changing their settings.
Both clients have local idle expiry disabled.

Binding sockets in advance is a capture-isolation measure, not a new protocol
implementation. A scoped socket factory returns the reserved socket for the
selected CDN address; HTTPcore continues to perform the normal TLS handshake
and HTTP/2 request. Certificate verification remains enabled and TLS key logging
is disabled for these contexts. The capture retains encrypted TLS prefixes,
not decrypted requests, signed URL parameters, or file payloads.

For 95 seconds after the initial reads, the diagnostic passively reads incoming
HTTP/2 frames using HTTPcore's decoder. It does not invoke HTTPcore's write path
or send an HTTP request or HTTP/2 PING. This lets GOAWAY decode time be correlated
with packet timestamps instead of waiting until the next application request.
The original control events are preserved; opaque/debug payloads are omitted.
Both client sockets remain open until the capture has stopped, so their final
cleanup cannot be mistaken for a server-initiated FIN.

The output directory contains:

- `packets.pcapng`: bounded packet capture, including encrypted TLS prefixes.
- `capture.log`: tcpdump capture counts, dropped-packet count, and startup errors.
- `report.json`: route, socket options, initial requests, passive HTTP/2 events,
  and a selected packet-header table decoded by the installed tshark.

Interpret TCP sequence numbers and lengths as well as tshark's
`tcp.analysis.keep_alive` and `tcp.analysis.keep_alive_ack` annotations. Probe
intervals after a successful acknowledgement differ from retry intervals after
a missing acknowledgement. A configured timer alone is not proof of emitted
packets. GOAWAY observation establishes HTTP/2 peer retirement, not its reason.

Packet timestamps use wall time. Application events use a monotonic origin;
`epoch_zero_ns` maps that origin approximately to wall time. These timestamps
are observation times, not isolated server processing times. The fixed IPv4
and passive-read diagnostic are deliberately narrower than normal API routing.

An initial `pktap,all` observation raised its snapshot length to 524288 bytes and
reported kernel drops. It retained encrypted TLS data, not decrypted content,
but could not establish missing-packet claims or the requested snapshot budget.
The revised capture uses the actual route interface, a larger capture buffer,
and explicit quality validation. Do not treat the initial run as a clean
absence-of-FIN/RST control.

Regression tests cover passive observation without writes, exception-safe
socket-factory restoration, unreadable startup process metadata, and invalid
capture scope rejection:

```sh
.venv/bin/python -m pytest test/test_tcp_keepalive_capture.py -q
```
