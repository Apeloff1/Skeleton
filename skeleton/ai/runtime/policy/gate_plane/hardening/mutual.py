"""mTLS-style mutual authentication for s2s calls.

Two complementary mechanisms, both optional and fail-closed when required:

1. **Peer certificate identity** (real mTLS terminated by the ASGI server
   or a trusted sidecar):

   * ASGI TLS extension — ``scope["extensions"]["tls"]["client_cert_chain"]``
     (PEM strings, leaf first).
   * ``X-Forwarded-Client-Cert`` (Envoy XFCC) — honoured **only** when the
     immediate peer address is inside ``trusted_proxies``; otherwise the
     header is ignored (a client could forge it).

   The leaf certificate is reduced to a SHA-256 thumbprint (hex) plus an
   optional SPIFFE ID (``spiffe://<trust-domain>/...``), which
   :class:`SpiffeMap` turns into a service name.

2. **Signed requests** (proof-of-possession where TLS is not end to end):
   ``x-s2s-signature: v1;kid=<kid>;t=<unix>;n=<nonce>;sig=<b64url>`` is an
   HMAC-SHA256 over a canonical request (method, path, query, body digest,
   request id, audience, timestamp, nonce) keyed by the caller's
   :class:`~skeleton.gate_plane.s2s.keyring.KeyRing`. Timestamps must fall
   within ``tolerance_s`` and nonces are single use.

:class:`MutualAuthPolicy` combines the peer identity with the verified
token: ``off`` ignores peers, ``optional`` checks whatever is presented,
``required`` rejects calls without a matching peer (globally or for named
services).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import unquote

from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import validate_service_name

XFCC_HEADER = "x-forwarded-client-cert"
SIGNATURE_HEADER = "x-s2s-signature"
SIGNATURE_VERSION = "v1"
DEFAULT_TOLERANCE_S = 60.0
MAX_XFCC_BYTES = 16_384
_SPIFFE_RE = re.compile(r"^spiffe://([a-z0-9._-]{1,255})(/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*)?$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", re.S)

Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class MutualAuthMode(str, Enum):
    OFF = "off"
    OPTIONAL = "optional"
    REQUIRED = "required"


class MutualAuthCode(str, Enum):
    OK = "ok"
    NO_PEER = "no_peer"
    UNTRUSTED_PROXY = "untrusted_proxy"
    BAD_XFCC = "bad_xfcc"
    BAD_CERT = "bad_cert"
    UNKNOWN_PEER = "unknown_peer"
    PEER_MISMATCH = "peer_mismatch"
    BAD_SIGNATURE_HEADER = "bad_signature_header"
    SIGNATURE_SKEW = "signature_skew"
    SIGNATURE_REPLAY = "signature_replay"
    SIGNATURE_UNKNOWN_KID = "signature_unknown_kid"
    SIGNATURE_INVALID = "signature_invalid"


@dataclass(frozen=True)
class PeerCertificate:
    thumbprint: str  # lowercase hex SHA-256 of the DER leaf certificate
    source: str  # tls | xfcc
    spiffe_id: Optional[str] = None
    subject: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "thumbprint": self.thumbprint,
            "source": self.source,
            "spiffe_id": self.spiffe_id,
            "subject": self.subject,
        }


def thumbprint_from_der(der: bytes) -> str:
    if not isinstance(der, (bytes, bytearray)) or not der:
        raise ValueError("certificate DER must be non-empty bytes")
    return hashlib.sha256(bytes(der)).hexdigest()


def pem_to_der(pem: str) -> bytes:
    m = _PEM_RE.search(pem or "")
    if not m:
        raise ValueError("no PEM certificate block")
    body = "".join(m.group(1).split())
    try:
        return base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("PEM body is not base64") from exc


def spiffe_ids_from_der(der: bytes) -> List[str]:
    """URI SANs that look like SPIFFE IDs (needs ``cryptography``; else ``[]``)."""
    try:
        from cryptography import x509
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    try:
        cert = x509.load_der_x509_certificate(der)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except Exception:  # noqa: BLE001 - no SAN / unparsable
        return []
    out: List[str] = []
    for uri in san.value.get_values_for_type(x509.UniformResourceIdentifier):
        if _SPIFFE_RE.match(uri):
            out.append(uri)
    return out


def _split_unquoted(text: str, sep: str) -> List[str]:
    """Split on ``sep`` outside double quotes (XFCC grammar)."""
    parts: List[str] = []
    buf: List[str] = []
    quoted = False
    escaped = False
    for ch in text:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\" and quoted:
            escaped = True
            buf.append(ch)
            continue
        if ch == '"':
            quoted = not quoted
            buf.append(ch)
            continue
        if ch == sep and not quoted:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if quoted:
        raise ValueError("unterminated quote")
    parts.append("".join(buf))
    return parts


def parse_xfcc(header: str) -> List[Dict[str, List[str]]]:
    """Parse an Envoy ``x-forwarded-client-cert`` header into elements.

    Each element maps lower-cased keys (``by``, ``hash``, ``cert``, ``chain``,
    ``subject``, ``uri``, ``dns``) to their values (keys may repeat).
    """
    if not isinstance(header, str) or not header.strip():
        raise ValueError("empty XFCC header")
    if len(header) > MAX_XFCC_BYTES:
        raise ValueError("XFCC header too large")
    elements: List[Dict[str, List[str]]] = []
    for raw_el in _split_unquoted(header, ","):
        el: Dict[str, List[str]] = {}
        for pair in _split_unquoted(raw_el, ";"):
            pair = pair.strip()
            if not pair:
                continue
            key, eq, value = pair.partition("=")
            if not eq or not key.strip():
                raise ValueError(f"bad XFCC pair {pair[:32]!r}")
            value = value.strip()
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1].replace('\\"', '"')
            el.setdefault(key.strip().lower(), []).append(value)
        if el:
            elements.append(el)
    if not elements:
        raise ValueError("XFCC header has no elements")
    return elements


@dataclass(frozen=True)
class SpiffeMap:
    """Maps SPIFFE IDs in one trust domain to service names.

    ``explicit`` wins; otherwise ``path_prefix`` + ``<service>`` (default
    ``/svc/<service>``) or the Kubernetes-style ``/ns/<ns>/sa/<service>``.
    """

    trust_domain: str
    explicit: Mapping[str, str] = field(default_factory=dict)
    path_prefix: str = "/svc/"
    allow_k8s_sa: bool = True
    namespaces: Optional[FrozenSet[str]] = None

    def service_for(self, spiffe_id: Optional[str]) -> Optional[str]:
        if not spiffe_id:
            return None
        if spiffe_id in self.explicit:
            return self.explicit[spiffe_id]
        m = _SPIFFE_RE.match(spiffe_id)
        if not m or m.group(1) != self.trust_domain:
            return None
        path = m.group(2) or ""
        candidate: Optional[str] = None
        if self.path_prefix and path.startswith(self.path_prefix):
            candidate = path[len(self.path_prefix):]
        elif self.allow_k8s_sa:
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "ns" and parts[2] == "sa":
                if self.namespaces is not None and parts[1] not in self.namespaces:
                    return None
                candidate = parts[3]
        if candidate is None or "/" in candidate:
            return None
        try:
            return validate_service_name(candidate)
        except ValueError:
            return None


def _parse_networks(cidrs: Iterable[str]) -> Tuple[Network, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


@dataclass(frozen=True)
class PeerResult:
    code: MutualAuthCode
    peer: Optional[PeerCertificate] = None
    service: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.code is MutualAuthCode.OK


class PeerExtractor:
    """Pulls the client certificate identity from an ASGI scope / headers."""

    def __init__(
        self,
        *,
        trusted_proxies: Iterable[str] = (),
        accept_asgi_tls: bool = True,
        xfcc_header: str = XFCC_HEADER,
        xfcc_element: str = "last",
        spiffe: Optional[SpiffeMap] = None,
    ) -> None:
        if xfcc_element not in ("first", "last"):
            raise ValueError("xfcc_element must be 'first' or 'last'")
        self.trusted_proxies = _parse_networks(trusted_proxies)
        self.accept_asgi_tls = bool(accept_asgi_tls)
        self.xfcc_header = xfcc_header.lower()
        self.xfcc_element = xfcc_element
        self.spiffe = spiffe

    def _client_trusted(self, client: Optional[Sequence[Any]]) -> bool:
        if not self.trusted_proxies or not client:
            return False
        try:
            addr = ipaddress.ip_address(str(client[0]))
        except ValueError:
            return False
        return any(addr in net for net in self.trusted_proxies)

    def _resolve_service(self, spiffe_id: Optional[str]) -> Optional[str]:
        return None if self.spiffe is None else self.spiffe.service_for(spiffe_id)

    def from_tls(self, scope: Mapping[str, Any]) -> Optional[PeerResult]:
        if not self.accept_asgi_tls:
            return None
        tls = ((scope.get("extensions") or {}).get("tls")) or {}
        chain = tls.get("client_cert_chain") or []
        if not chain:
            return None
        try:
            der = pem_to_der(str(chain[0]))
        except ValueError:
            return PeerResult(MutualAuthCode.BAD_CERT)
        ids = spiffe_ids_from_der(der)
        spiffe_id = ids[0] if ids else None
        peer = PeerCertificate(
            thumbprint=thumbprint_from_der(der), source="tls", spiffe_id=spiffe_id,
            subject=tls.get("client_cert_name") if isinstance(tls.get("client_cert_name"), str) else None,
        )
        return PeerResult(MutualAuthCode.OK, peer, self._resolve_service(spiffe_id))

    def from_xfcc(self, headers: Mapping[str, str], client: Optional[Sequence[Any]]) -> Optional[PeerResult]:
        low = {str(k).lower(): str(v) for k, v in headers.items()}
        raw = low.get(self.xfcc_header)
        if raw is None:
            return None
        if not self._client_trusted(client):
            return PeerResult(MutualAuthCode.UNTRUSTED_PROXY)
        try:
            elements = parse_xfcc(raw)
        except ValueError:
            return PeerResult(MutualAuthCode.BAD_XFCC)
        el = elements[-1] if self.xfcc_element == "last" else elements[0]
        thumb: Optional[str] = None
        if el.get("hash"):
            h = el["hash"][0].strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", h):
                thumb = h
        if thumb is None and el.get("cert"):
            try:
                thumb = thumbprint_from_der(pem_to_der(unquote(el["cert"][0])))
            except ValueError:
                return PeerResult(MutualAuthCode.BAD_CERT)
        if thumb is None:
            return PeerResult(MutualAuthCode.BAD_XFCC)
        spiffe_id = next((u for u in el.get("uri", []) if _SPIFFE_RE.match(u)), None)
        subject = el["subject"][0] if el.get("subject") else None
        peer = PeerCertificate(thumbprint=thumb, source="xfcc", spiffe_id=spiffe_id, subject=subject)
        return PeerResult(MutualAuthCode.OK, peer, self._resolve_service(spiffe_id))

    def extract(self, scope: Mapping[str, Any], headers: Mapping[str, str]) -> PeerResult:
        """TLS extension first (it cannot be forged by the client), then XFCC."""
        tls = self.from_tls(scope)
        if tls is not None:
            return tls
        xfcc = self.from_xfcc(headers, scope.get("client"))
        if xfcc is not None:
            return xfcc
        return PeerResult(MutualAuthCode.NO_PEER)


@dataclass(frozen=True)
class MutualAuthPolicy:
    mode: MutualAuthMode = MutualAuthMode.OFF
    required_for: FrozenSet[str] = frozenset()
    require_known_peer: bool = True
    pinned_thumbprints: Mapping[str, FrozenSet[str]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        mode: Union[str, MutualAuthMode] = MutualAuthMode.OFF,
        *,
        required_for: Iterable[str] = (),
        require_known_peer: bool = True,
        pinned_thumbprints: Optional[Mapping[str, Iterable[str]]] = None,
    ) -> "MutualAuthPolicy":
        pins = {
            validate_service_name(svc): frozenset(t.lower() for t in thumbs)
            for svc, thumbs in (pinned_thumbprints or {}).items()
        }
        return cls(
            mode=MutualAuthMode(mode),
            required_for=frozenset(validate_service_name(s) for s in required_for),
            require_known_peer=bool(require_known_peer),
            pinned_thumbprints=pins,
        )

    def required(self, service: Optional[str]) -> bool:
        if self.mode is MutualAuthMode.REQUIRED:
            return True
        return service is not None and service in self.required_for

    def evaluate(self, peer: PeerResult, token_service: Optional[str]) -> MutualAuthCode:
        """Check ``peer`` against the token's issuer. Returns ``OK`` or a failure code."""
        if self.mode is MutualAuthMode.OFF and not self.required_for:
            return MutualAuthCode.OK
        required = self.required(token_service)
        if peer.code is MutualAuthCode.NO_PEER:
            return MutualAuthCode.NO_PEER if required else MutualAuthCode.OK
        if not peer.ok:
            # A *presented but broken* credential is always rejected.
            return peer.code
        assert peer.peer is not None
        if token_service is not None:
            pins = self.pinned_thumbprints.get(token_service)
            if pins is not None and peer.peer.thumbprint not in pins:
                return MutualAuthCode.PEER_MISMATCH
            if peer.service is not None and peer.service != token_service:
                return MutualAuthCode.PEER_MISMATCH
            if peer.service is None and pins is None and required and self.require_known_peer:
                return MutualAuthCode.UNKNOWN_PEER
        return MutualAuthCode.OK


# -- signed requests (proof of possession) ---------------------------------


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body or b"").hexdigest()


def canonical_request(
    *,
    method: str,
    path: str,
    query: str,
    body: bytes,
    request_id: str,
    audience: str,
    timestamp: int,
    nonce: str,
) -> bytes:
    lines = [
        SIGNATURE_VERSION,
        (method or "GET").upper(),
        path or "/",
        "&".join(sorted(p for p in (query or "").split("&") if p)),
        body_digest(body),
        request_id or "",
        audience,
        str(int(timestamp)),
        nonce,
    ]
    return "\n".join(lines).encode("utf-8")


@dataclass(frozen=True)
class ParsedSignature:
    kid: str
    timestamp: int
    nonce: str
    sig: bytes


def parse_signature_header(raw: str) -> ParsedSignature:
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError("signature header missing or too long")
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if not parts or parts[0] != SIGNATURE_VERSION:
        raise ValueError("unsupported signature version")
    fields: Dict[str, str] = {}
    for p in parts[1:]:
        k, eq, v = p.partition("=")
        if not eq or k in fields:
            raise ValueError("malformed or duplicate signature field")
        fields[k] = v
    if set(fields) != {"kid", "t", "n", "sig"}:
        raise ValueError("signature needs exactly kid, t, n, sig")
    if not fields["t"].isdigit():
        raise ValueError("t must be unix seconds")
    if not _NONCE_RE.match(fields["n"]):
        raise ValueError("bad nonce")
    sig_txt = fields["sig"]
    try:
        sig = base64.urlsafe_b64decode(sig_txt + "=" * (-len(sig_txt) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("sig is not base64url") from exc
    if len(sig) != 32:
        raise ValueError("sig must be an HMAC-SHA256 digest")
    return ParsedSignature(kid=fields["kid"], timestamp=int(fields["t"]), nonce=fields["n"], sig=sig)


class NonceCache:
    """Bounded single-use nonce cache keyed by (kid, nonce)."""

    def __init__(self, capacity: int = 100_000) -> None:
        self.capacity = int(capacity)
        self._seen: "OrderedDict[Tuple[str, str], float]" = OrderedDict()
        self._lock = threading.Lock()

    def check_and_add(self, kid: str, nonce: str, expires_at: float, now: float) -> bool:
        with self._lock:
            while self._seen:
                k, exp = next(iter(self._seen.items()))
                if exp > now:
                    break
                del self._seen[k]
            key = (kid, nonce)
            if key in self._seen and self._seen[key] > now:
                return False
            self._seen[key] = expires_at
            self._seen.move_to_end(key)
            while len(self._seen) > self.capacity:
                self._seen.popitem(last=False)
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)


class RequestSigner:
    """Signs outbound requests with the caller's ACTIVE key."""

    def __init__(self, keyring: KeyRing, *, clock: Optional[Clock] = None) -> None:
        self.keyring = keyring
        self.clock: Clock = clock or system_clock()

    def sign(
        self,
        *,
        method: str,
        path: str,
        audience: str,
        body: bytes = b"",
        query: str = "",
        request_id: str = "",
        nonce: Optional[str] = None,
    ) -> str:
        key = self.keyring.signing_key()
        ts = int(self.clock.now())
        n = nonce or secrets.token_urlsafe(18)
        msg = canonical_request(
            method=method, path=path, query=query, body=body, request_id=request_id,
            audience=validate_service_name(audience), timestamp=ts, nonce=n,
        )
        sig = hmac.new(key.secret, msg, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        return f"{SIGNATURE_VERSION};kid={key.kid};t={ts};n={n};sig={sig_b64}"


@dataclass(frozen=True)
class SignatureResult:
    code: MutualAuthCode
    kid: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.code is MutualAuthCode.OK


class RequestVerifier:
    """Verifies ``x-s2s-signature`` against a key ring with skew + replay checks."""

    def __init__(
        self,
        audience: str,
        keyring: KeyRing,
        *,
        clock: Optional[Clock] = None,
        tolerance_s: float = DEFAULT_TOLERANCE_S,
        nonces: Optional[NonceCache] = None,
    ) -> None:
        if not 0 < tolerance_s <= 900:
            raise ValueError("tolerance_s must be within (0, 900]")
        self.audience = validate_service_name(audience)
        self.keyring = keyring
        self.clock: Clock = clock or system_clock()
        self.tolerance_s = float(tolerance_s)
        self.nonces = nonces or NonceCache()

    def verify(
        self,
        header: Optional[str],
        *,
        method: str,
        path: str,
        body: bytes = b"",
        query: str = "",
        request_id: str = "",
    ) -> SignatureResult:
        if header is None:
            return SignatureResult(MutualAuthCode.NO_PEER)
        try:
            parsed = parse_signature_header(header)
        except ValueError:
            return SignatureResult(MutualAuthCode.BAD_SIGNATURE_HEADER)
        now = self.clock.now()
        if abs(now - parsed.timestamp) > self.tolerance_s:
            return SignatureResult(MutualAuthCode.SIGNATURE_SKEW, parsed.kid)
        key = self.keyring.verification_key(parsed.kid)
        if key is None:
            return SignatureResult(MutualAuthCode.SIGNATURE_UNKNOWN_KID, parsed.kid)
        msg = canonical_request(
            method=method, path=path, query=query, body=body, request_id=request_id,
            audience=self.audience, timestamp=parsed.timestamp, nonce=parsed.nonce,
        )
        if not hmac.compare_digest(hmac.new(key.secret, msg, hashlib.sha256).digest(), parsed.sig):
            return SignatureResult(MutualAuthCode.SIGNATURE_INVALID, parsed.kid)
        # Nonce is consumed only after the MAC checks out, so garbage cannot
        # evict legitimate nonces.
        if not self.nonces.check_and_add(parsed.kid, parsed.nonce, parsed.timestamp + self.tolerance_s, now):
            return SignatureResult(MutualAuthCode.SIGNATURE_REPLAY, parsed.kid)
        return SignatureResult(MutualAuthCode.OK, parsed.kid)


__all__ = [
    "DEFAULT_TOLERANCE_S",
    "MutualAuthCode",
    "MutualAuthMode",
    "MutualAuthPolicy",
    "NonceCache",
    "ParsedSignature",
    "PeerCertificate",
    "PeerExtractor",
    "PeerResult",
    "RequestSigner",
    "RequestVerifier",
    "SIGNATURE_HEADER",
    "SignatureResult",
    "SpiffeMap",
    "XFCC_HEADER",
    "body_digest",
    "canonical_request",
    "parse_signature_header",
    "parse_xfcc",
    "pem_to_der",
    "spiffe_ids_from_der",
    "thumbprint_from_der",
]
