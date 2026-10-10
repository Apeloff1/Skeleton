"""Destination allowlist and SSRF guard for outbound callbacks.

A callback URL is delivered only if **all** hold:

* scheme is ``https`` (``http`` only when ``allow_http`` — dev/test);
* no userinfo (``user:pass@``), no fragment, length within ``max_url_len``;
* the host matches an allowlist entry — exact (``hooks.example.com``) or
  suffix wildcard (``*.example.com``, which does **not** match the apex);
* the port is in ``allowed_ports`` (default 443, plus 80 with ``allow_http``);
* every address the host resolves to is public: loopback, private (RFC
  1918 / ULA), link-local (incl. cloud metadata ``169.254.169.254``),
  multicast, reserved, unspecified and CGNAT ranges are refused unless
  explicitly listed in ``allowed_networks``. IP-literal hosts are checked
  the same way.

Resolution goes through an injectable ``resolver(host) -> [ip, ...]`` so
tests and the chaos suite never touch DNS. The resolved address set is
returned with the verdict so a transport can pin the connection to the
checked addresses (closing the DNS-rebinding window).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Callable, FrozenSet, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
Resolver = Callable[[str], Sequence[str]]

DEFAULT_MAX_URL_LEN = 2048
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class EgressDenyReason(str, Enum):
    OK = "ok"
    BAD_URL = "bad_url"
    SCHEME = "scheme_not_allowed"
    USERINFO = "userinfo_not_allowed"
    FRAGMENT = "fragment_not_allowed"
    TOO_LONG = "url_too_long"
    HOST = "host_not_allowlisted"
    PORT = "port_not_allowed"
    RESOLVE = "resolve_failed"
    PRIVATE_ADDRESS = "private_address"


@dataclass(frozen=True)
class EgressVerdict:
    allowed: bool
    reason: EgressDenyReason
    host: Optional[str] = None
    port: Optional[int] = None
    addresses: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value,
            "host": self.host,
            "port": self.port,
            "addresses": list(self.addresses),
        }


def system_resolver(host: str) -> List[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    out: List[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in out:
            out.append(addr)
    return out


def is_public_address(addr: IPAddress) -> bool:
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return is_public_address(addr.ipv4_mapped)
    if (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        return False
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT:
        return False
    return True


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".example.com"
        return host.endswith(suffix) and len(host) > len(suffix)
    return host == pattern


class EgressAllowlist:
    def __init__(
        self,
        hosts: Iterable[str],
        *,
        allow_http: bool = False,
        allowed_ports: Optional[Iterable[int]] = None,
        allowed_networks: Iterable[str] = (),
        resolver: Optional[Resolver] = None,
        max_url_len: int = DEFAULT_MAX_URL_LEN,
    ) -> None:
        patterns = []
        for h in hosts:
            h = h.strip().lower().rstrip(".")
            if not h or "/" in h or "@" in h or (h.count("*") and not (h.startswith("*.") and h.count("*") == 1)):
                raise ValueError(f"bad allowlist host pattern {h!r}")
            patterns.append(h)
        self.hosts: Tuple[str, ...] = tuple(patterns)
        self.allow_http = bool(allow_http)
        ports = set(allowed_ports) if allowed_ports is not None else ({443, 80} if allow_http else {443})
        self.allowed_ports: FrozenSet[int] = frozenset(int(p) for p in ports)
        self.allowed_networks: Tuple[IPNetwork, ...] = tuple(
            ipaddress.ip_network(n, strict=False) for n in allowed_networks
        )
        self.resolver: Resolver = resolver or system_resolver
        self.max_url_len = int(max_url_len)

    def host_allowed(self, host: str) -> bool:
        h = host.lower().rstrip(".")
        return any(_host_matches(h, p) for p in self.hosts)

    def _address_ok(self, addr: IPAddress) -> bool:
        if any(addr in net for net in self.allowed_networks):
            return True
        return is_public_address(addr)

    def check(self, url: str) -> EgressVerdict:
        if not isinstance(url, str) or not url:
            return EgressVerdict(False, EgressDenyReason.BAD_URL)
        if len(url) > self.max_url_len:
            return EgressVerdict(False, EgressDenyReason.TOO_LONG)
        if any(ord(c) < 0x21 or ord(c) == 0x7F for c in url):
            return EgressVerdict(False, EgressDenyReason.BAD_URL)
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return EgressVerdict(False, EgressDenyReason.BAD_URL)
        scheme = parts.scheme.lower()
        if scheme not in ("https", "http") or (scheme == "http" and not self.allow_http):
            return EgressVerdict(False, EgressDenyReason.SCHEME)
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            return EgressVerdict(False, EgressDenyReason.USERINFO)
        if parts.fragment:
            return EgressVerdict(False, EgressDenyReason.FRAGMENT)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            return EgressVerdict(False, EgressDenyReason.BAD_URL)
        eff_port = port if port is not None else (443 if scheme == "https" else 80)
        if not self.host_allowed(host):
            return EgressVerdict(False, EgressDenyReason.HOST, host=host, port=eff_port)
        if eff_port not in self.allowed_ports:
            return EgressVerdict(False, EgressDenyReason.PORT, host=host, port=eff_port)
        try:
            literal: Optional[IPAddress] = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            addrs = [literal]
        else:
            try:
                resolved = list(self.resolver(host))
                addrs = [ipaddress.ip_address(a) for a in resolved]
            except Exception:  # noqa: BLE001 - any resolver failure denies
                return EgressVerdict(False, EgressDenyReason.RESOLVE, host=host, port=eff_port)
            if not addrs:
                return EgressVerdict(False, EgressDenyReason.RESOLVE, host=host, port=eff_port)
        if not all(self._address_ok(a) for a in addrs):
            return EgressVerdict(False, EgressDenyReason.PRIVATE_ADDRESS, host=host, port=eff_port)
        return EgressVerdict(
            True, EgressDenyReason.OK, host=host, port=eff_port, addresses=tuple(str(a) for a in addrs)
        )


__all__ = [
    "EgressAllowlist",
    "EgressDenyReason",
    "EgressVerdict",
    "Resolver",
    "is_public_address",
    "system_resolver",
]
