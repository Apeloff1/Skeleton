"""Local-only request boundary: no browser origins, proxies or public hostnames."""
from __future__ import annotations

import hmac
import ipaddress
from typing import Mapping

from .errors import deny
from .contracts import strict_integer


class LoopbackGate:
    def __init__(self, bearer: str, *, max_body: int = 131072):
        if type(bearer) is not str or not 32 <= len(bearer) <= 512:
            deny("bearer-invalid")
        if not bearer.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in bearer):
            deny("bearer-invalid")
        self._bearer = bearer
        self.max_body = strict_integer(max_body, minimum=1024, maximum=1048576, field="body-limit")

    def authorize(
        self,
        *,
        peer_ip: str,
        host: str,
        method: str,
        route: str,
        headers: Mapping[str, str],
        body_length: int,
    ) -> None:
        try:
            ip = ipaddress.ip_address(peer_ip)
            host_ip = ipaddress.ip_address(host)
        except (ValueError, TypeError):
            deny("transport-host")
        if not ip.is_loopback or not host_ip.is_loopback:
            deny("transport-remote")
        if method != "POST" or route != "/v1/operations":
            deny("transport-route")
        strict_integer(body_length, minimum=0, maximum=self.max_body, field="body-limit")
        if type(headers) is not dict or any(type(k) is not str or type(v) is not str for k, v in headers.items()):
            deny("transport-header")
        keys = {k.lower(): v for k, v in headers.items()}
        if len(keys) != len(headers):
            deny("transport-header-duplicate")
        if any(k in keys for k in ("origin", "forwarded", "x-forwarded-host", "x-forwarded-for")):
            deny("transport-browser-proxy")
        if keys.get("content-type") != "application/json":
            deny("transport-content-type")
        token = keys.get("authorization", "")
        if not token.startswith("Bearer ") or not hmac.compare_digest(token[7:], self._bearer):
            deny("transport-bearer")
