"""Production HTTP transport with redirect and destination safety controls."""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .core import FetchResponse, canonicalize_url, destination_allowed


class UnsafeDestination(ValueError):
    pass


def _validate_destination(url: str, allowed_hosts: frozenset[str] | None = None) -> str:
    url = canonicalize_url(url)
    p = urlsplit(url)
    host = p.hostname or ""
    if allowed_hosts is not None and host.lower() not in allowed_hosts:
        raise UnsafeDestination("destination host is outside crawler allowlist")
    if not destination_allowed(host):
        raise UnsafeDestination("non-public destination rejected")
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeDestination("destination DNS resolution failed") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or any(not destination_allowed(address) for address in addresses):
        raise UnsafeDestination("DNS resolved to a non-public destination")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class SafeHttpFetcher:
    """Small bounded HTTP client.

    Redirects are followed manually so every hop is canonicalized, allowlisted and
    DNS-checked before access. urllib still provides TLS certificate validation.
    """

    timeout_seconds: float = 15.0
    max_redirects: int = 5
    allowed_hosts: frozenset[str] | None = None

    def fetch(self, url: str, *, user_agent: str, max_bytes: int) -> FetchResponse:
        current = _validate_destination(url, self.allowed_hosts)
        opener = urllib.request.build_opener(_NoRedirect)
        for hop in range(self.max_redirects + 1):
            request = urllib.request.Request(
                current,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                },
                method="GET",
            )
            try:
                response = opener.open(request, timeout=self.timeout_seconds)
            except urllib.error.HTTPError as exc:
                response = exc
            status = int(response.status)
            headers = {k.lower(): v for k, v in response.headers.items()}
            if status in {301, 302, 303, 307, 308}:
                location = headers.get("location")
                response.close()
                if not location or hop >= self.max_redirects:
                    raise UnsafeDestination("redirect limit or malformed redirect")
                current = _validate_destination(urljoin(current, location), self.allowed_hosts)
                continue
            length = headers.get("content-length")
            if length:
                try:
                    if int(length) > max_bytes:
                        response.close()
                        raise ValueError("response exceeds configured byte limit")
                except ValueError as exc:
                    response.close()
                    raise ValueError("invalid or excessive Content-Length") from exc
            body = response.read(max_bytes + 1)
            response.close()
            if len(body) > max_bytes:
                raise ValueError("response exceeds configured byte limit")
            return FetchResponse(
                url=current,
                status=status,
                headers=headers,
                body=body,
                fetched_at=time.time(),
            )
        raise UnsafeDestination("redirect limit exceeded")
