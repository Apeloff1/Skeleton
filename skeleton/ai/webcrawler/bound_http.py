"""Deadline-bound HTTP, direct DNS pinning and configured proxy admission."""

from __future__ import annotations

import base64
import http.client
import math
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from .core import FetchResponse
from .dns_binding import (
    ResolvedTarget,
    peer_is_planned,
    resolve_addresses,
    resolve_target,
)


class BoundConnectionError(ConnectionError):
    pass


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, target: ResolvedTarget, timeout, *, deadline=None):
        super().__init__(target.host, target.port, timeout=timeout)
        self.target = target
        self.deadline = deadline or time.monotonic() + timeout

    def connect(self):
        last = None
        for address in self.target.addresses:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("crawler connection deadline exceeded")
            sock = socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(remaining)
                sock.connect((address, self.target.port))
                if time.monotonic() >= self.deadline:
                    sock.close()
                    raise TimeoutError("crawler connection deadline exceeded")
                if not peer_is_planned(sock.getpeername()[0], self.target):
                    sock.close()
                    raise BoundConnectionError("connected peer outside validated DNS set")
                self.sock = sock
                return
            except OSError as exc:
                sock.close()
                last = exc
        raise BoundConnectionError("no validated address connected") from last


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    def __init__(self, target, timeout, context, *, deadline=None, origin_host=None):
        super().__init__(target, timeout, deadline=deadline)
        self.context = context
        self.origin_host = origin_host or target.host

    def connect(self):
        super().connect()
        if self._tunnel_host:
            self.sock.settimeout(max(0.01, self.deadline - time.monotonic()))
            self._tunnel()
        self.sock.settimeout(max(0.01, self.deadline - time.monotonic()))
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.origin_host)


@dataclass
class SocketBoundFetcher:
    timeout_seconds: float = 10.0
    allowed_hosts: frozenset[str] | None = None
    ssl_context: ssl.SSLContext | None = None
    proxy_url: str | None = None

    @property
    def transport_mode(self):
        return "configured_proxy_public_origin_guard" if self.proxy_url else "direct_dns_socket_pinned"

    def fetch_once(self, url, *, user_agent, max_bytes, extra_headers=None):
        if type(max_bytes) is not int or not 0 <= max_bytes <= 4_000_000:
            raise ValueError("invalid response byte bound")
        if (
            isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 30
        ):
            raise ValueError("invalid transport timeout")
        deadline = time.monotonic() + self.timeout_seconds
        target = resolve_target(url, self.allowed_hosts, timeout_seconds=min(8, self.timeout_seconds))
        parsed = urlsplit(target.url)
        context = self.ssl_context or ssl.create_default_context()
        host_header = f"[{target.host}]" if ":" in target.host else target.host
        if parsed.port is not None:
            host_header += f":{parsed.port}"
        headers = {
            "Host": host_header,
            "User-Agent": user_agent,
            "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        for key, value in (extra_headers or {}).items():
            if (
                key.lower() not in {"if-none-match", "if-modified-since"}
                or not isinstance(value, str)
                or len(value) > 1024
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("unsupported crawler request header")
            headers[key] = value
        proxy_auth = {}
        if self.proxy_url:
            proxy = urlsplit(self.proxy_url if "://" in self.proxy_url else "http://" + self.proxy_url)
            if (
                proxy.scheme != "http"
                or not proxy.hostname
                or proxy.path not in {"", "/"}
                or proxy.query
                or proxy.fragment
            ):
                raise ValueError("only configured HTTP proxy endpoints are supported")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("crawler proxy admission deadline exceeded")
            addresses = resolve_addresses(
                proxy.hostname, proxy.port or 80, timeout_seconds=min(3, remaining), allow_private=True
            )
            connection_target = ResolvedTarget(
                "configured-egress-proxy", proxy.hostname, proxy.port or 80, addresses
            )
            if proxy.username is not None:
                raw = f"{unquote(proxy.username)}:{unquote(proxy.password or '')}"
                proxy_auth["Proxy-Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode("ascii")
        else:
            connection_target = target
        if parsed.scheme == "https":
            conn = _PinnedHTTPSConnection(
                connection_target, self.timeout_seconds, context, deadline=deadline, origin_host=target.host
            )
            if self.proxy_url:
                # Keep the original public hostname visible to proxy policy;
                # never CONNECT to an IP to conceal an origin from egress rules.
                conn.set_tunnel(target.host, target.port, headers=proxy_auth)
        else:
            conn = _PinnedHTTPConnection(connection_target, self.timeout_seconds, deadline=deadline)
            if self.proxy_url:
                headers.update(proxy_auth)
        path = target.url if self.proxy_url and parsed.scheme == "http" else parsed.path or "/"
        if parsed.query and not (self.proxy_url and parsed.scheme == "http"):
            path += "?" + parsed.query

        def interrupt_socket():
            sock = conn.sock
            if sock is None:
                sock = getattr(getattr(getattr(response_holder[0], "fp", None), "raw", None), "_sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        response_holder = [None]
        watchdog = threading.Timer(max(0, deadline - time.monotonic()), interrupt_socket)
        watchdog.daemon = True
        watchdog.start()
        try:
            conn.request("GET", path, headers=headers)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("crawler header deadline exceeded")
            conn.sock.settimeout(remaining)
            response = conn.getresponse()
            response_holder[0] = response
            response_headers = response.getheaders()
            if sum(len(key) + len(value) for key, value in response_headers) > 32768:
                raise ValueError("response header bound exceeded")
            if sum(key.lower() == "content-length" for key, _ in response_headers) > 1:
                raise ValueError("ambiguous Content-Length headers")
            out_headers = {key.lower(): value for key, value in response_headers}
            if "content-length" in out_headers and "transfer-encoding" in out_headers:
                raise ValueError("ambiguous response framing")
            if response.status in {301, 302, 303, 307, 308}:
                body = b""
            else:
                if out_headers.get("content-encoding", "identity").lower() not in {"identity", ""}:
                    raise ValueError("encoded crawler response is not admitted")
                length = out_headers.get("content-length")
                if length is not None:
                    try:
                        size = int(length)
                    except ValueError as exc:
                        raise ValueError("invalid Content-Length") from exc
                    if not 0 <= size <= max_bytes:
                        raise ValueError("response exceeds configured byte limit")
                chunks = []
                count = 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("crawler response deadline exceeded")
                    raw = getattr(getattr(response, "fp", None), "raw", None)
                    sock = getattr(raw, "_sock", None)
                    if sock is not None:
                        sock.settimeout(remaining)
                    chunk = response.read1(min(65536, max_bytes + 1 - count))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    count += len(chunk)
                    if count > max_bytes:
                        raise ValueError("response exceeds configured byte limit")
                body = b"".join(chunks)
                if response.length not in {None, 0}:
                    raise ValueError("incomplete response body")
            if time.monotonic() >= deadline:
                raise TimeoutError("crawler response deadline exceeded")
            return FetchResponse(target.url, int(response.status), out_headers, body, time.time())
        finally:
            watchdog.cancel()
            watchdog.join()
            conn.close()
