"""Canonical HTTP facade honoring configured egress without implicit redirects."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .core import canonicalize_url


class UnsafeDestination(ValueError):
    pass


def _validate_destination(url, allowed_hosts=None):
    from .dns_binding import resolve_target

    return resolve_target(url, allowed_hosts).url


@dataclass
class SafeHttpFetcher:
    timeout_seconds: float = 10.0
    max_redirects: int = 5
    allowed_hosts: frozenset[str] | None = None
    bind_dns_to_socket: bool = True
    respect_environment_proxy: bool = True

    @property
    def transport_mode(self):
        proxies = urllib.request.getproxies() if self.respect_environment_proxy else {}
        return (
            "configured_proxy_public_origin_guard"
            if any(proxies.get(s) for s in ("http", "https"))
            else "direct_dns_socket_pinned"
        )

    def fetch_once(self, url, *, user_agent, max_bytes, extra_headers=None):
        from .bound_http import SocketBoundFetcher

        url = canonicalize_url(url)
        proxies = urllib.request.getproxies() if self.respect_environment_proxy else {}
        proxy = proxies.get(urlsplit(url).scheme)
        if not proxy and not self.bind_dns_to_socket:
            raise UnsafeDestination("unbound direct crawler transport is disabled")
        # Environment proxy settings are deployment configuration, never request
        # fields. NO_PROXY cannot silently turn this into a direct Internet call.
        return SocketBoundFetcher(self.timeout_seconds, self.allowed_hosts, proxy_url=proxy).fetch_once(
            url, user_agent=user_agent, max_bytes=max_bytes, extra_headers=extra_headers
        )

    def fetch(self, url, *, user_agent, max_bytes):
        current = canonicalize_url(url)
        seen = set()
        for hop in range(self.max_redirects + 1):
            if current in seen:
                raise UnsafeDestination("redirect loop")
            seen.add(current)
            response = self.fetch_once(current, user_agent=user_agent, max_bytes=max_bytes)
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location or hop >= self.max_redirects:
                raise UnsafeDestination("redirect limit or malformed redirect")
            current = canonicalize_url(urljoin(current, location))
        raise UnsafeDestination("redirect limit exceeded")
