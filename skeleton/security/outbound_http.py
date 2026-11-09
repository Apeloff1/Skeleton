"""Peer-bound outbound HTTP policy primitives.

URL syntax validation and DNS pre-resolution are necessary but not sufficient for
SSRF defense. A client can validate a public DNS answer and still connect to a
different address after rebinding. This module closes that authority gap by
requiring every transport response to include the numeric peer address actually
used by the connection. The peer is checked against the immutable
ResolvedDestination snapshot from skeleton.security.outbound_url before any
response body is consumed.

The module is transport-neutral and dependency-free. HTTP libraries can be
adapted behind AsyncOutboundTransport while retaining their pooling/TLS stacks.
The adapter is responsible only for making one request with redirects disabled
and returning connection evidence.
"""
from __future__ import annotations

from collections.abc import AsyncIterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import re
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

from skeleton.security.outbound_url import (
    ResolvedDestination,
    Resolver,
    resolve_public_https_url,
    validate_connected_peer,
    validate_public_https_redirect,
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_\x60|~0-9A-Za-z]+$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class OutboundHttpError(RuntimeError):
    """Base class for bounded outbound HTTP errors."""


class OutboundHttpPolicyError(OutboundHttpError, ValueError):
    """Raised before transport use when request policy is invalid."""


class OutboundHttpEvidenceError(OutboundHttpError):
    """Raised when transport or response evidence is incomplete or inconsistent."""


class OutboundHttpLimitError(OutboundHttpError):
    """Raised when bounded response processing exceeds policy."""


@dataclass(frozen=True, slots=True)
class TimeoutBudget:
    connect_seconds: float = 5.0
    read_seconds: float = 10.0
    total_seconds: float = 20.0

    def __post_init__(self) -> None:
        for name in ("connect_seconds", "read_seconds", "total_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.connect_seconds > self.total_seconds:
            raise ValueError("connect timeout cannot exceed total timeout")
        if self.read_seconds > self.total_seconds:
            raise ValueError("read timeout cannot exceed total timeout")


@dataclass(frozen=True, slots=True)
class OutboundHttpPolicy:
    max_response_bytes: int = 2 * 1024 * 1024
    max_response_chunks: int = 32_768
    max_header_count: int = 128
    max_header_name_bytes: int = 128
    max_header_value_bytes: int = 8 * 1024
    max_total_header_bytes: int = 64 * 1024
    max_redirects: int = 4
    allow_cross_origin_redirects: bool = False
    allowed_methods: tuple[str, ...] = ("GET", "HEAD")
    accepted_content_types: tuple[str, ...] = ()
    timeout: TimeoutBudget = TimeoutBudget()

    def __post_init__(self) -> None:
        for name in (
            "max_response_bytes",
            "max_response_chunks",
            "max_header_count",
            "max_header_name_bytes",
            "max_header_value_bytes",
            "max_total_header_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.max_redirects, bool)
            or not isinstance(self.max_redirects, int)
            or not 0 <= self.max_redirects <= 16
        ):
            raise ValueError("max_redirects must be between 0 and 16")
        if not isinstance(self.allow_cross_origin_redirects, bool):
            raise ValueError("allow_cross_origin_redirects must be boolean")
        methods = tuple(_normalize_method(method) for method in self.allowed_methods)
        if not methods:
            raise ValueError("allowed_methods cannot be empty")
        if len(methods) != len(set(methods)):
            raise ValueError("allowed_methods contains duplicates")
        object.__setattr__(self, "allowed_methods", methods)
        content_types = tuple(_normalize_media_type(value) for value in self.accepted_content_types)
        if len(content_types) != len(set(content_types)):
            raise ValueError("accepted_content_types contains duplicates")
        object.__setattr__(self, "accepted_content_types", content_types)


@dataclass(frozen=True, slots=True)
class TransportRequest:
    method: str
    destination: ResolvedDestination
    headers: tuple[tuple[str, str], ...]
    timeout: TimeoutBudget


@dataclass(slots=True)
class TransportResponse:
    status_code: int
    headers: Sequence[tuple[str, str]]
    body: AsyncIterable[bytes]
    peer_address: str


class AsyncOutboundTransport(Protocol):
    """One-hop transport with automatic redirects explicitly disabled."""

    async def request(self, request: TransportRequest) -> TransportResponse:
        ...


@dataclass(frozen=True, slots=True)
class SafeHttpResponse:
    url: str
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    peer_address: str
    redirects: int

    def header(self, name: str) -> str | None:
        wanted = name.casefold()
        matches = [value for key, value in self.headers if key.casefold() == wanted]
        if not matches:
            return None
        if len(matches) > 1:
            raise OutboundHttpEvidenceError("response contains duplicate singleton header")
        return matches[0]

    def text(self, *, encoding: str = "utf-8") -> str:
        try:
            return self.body.decode(encoding)
        except (LookupError, UnicodeError) as exc:
            raise OutboundHttpEvidenceError("response text decoding failed") from exc

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (UnicodeError, ValueError) as exc:
            raise OutboundHttpEvidenceError("response JSON decoding failed") from exc


def _normalize_method(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("HTTP method must be text")
    method = value.strip().upper()
    if not method or method != value.upper() or not method.isascii() or not method.isalpha():
        raise ValueError("invalid HTTP method")
    return method


def _normalize_media_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("media type must be text")
    media_type = value.strip().lower()
    if not media_type or _CONTROL.search(media_type) or "/" not in media_type:
        raise ValueError("invalid media type")
    if ";" in media_type:
        media_type = media_type.split(";", 1)[0].strip()
    return media_type


def _validate_header(
    name: str,
    value: str,
    *,
    policy: OutboundHttpPolicy,
) -> tuple[str, str]:
    if not isinstance(name, str) or not isinstance(value, str):
        raise OutboundHttpEvidenceError("header names and values must be text")
    if not _HEADER_NAME.fullmatch(name):
        raise OutboundHttpEvidenceError("invalid header name")
    if _CONTROL.search(value):
        raise OutboundHttpEvidenceError("header value contains control characters")
    if len(name.encode("ascii")) > policy.max_header_name_bytes:
        raise OutboundHttpLimitError("header name exceeds byte bound")
    if len(value.encode("utf-8")) > policy.max_header_value_bytes:
        raise OutboundHttpLimitError("header value exceeds byte bound")
    return name.lower(), value


def _normalize_headers(
    headers: Sequence[tuple[str, str]] | Mapping[str, str],
    *,
    policy: OutboundHttpPolicy,
    request: bool,
) -> tuple[tuple[str, str], ...]:
    items = tuple(headers.items()) if isinstance(headers, Mapping) else tuple(headers)
    if len(items) > policy.max_header_count:
        raise OutboundHttpLimitError("header count exceeds bound")

    normalized: list[tuple[str, str]] = []
    total = 0
    seen_singletons: set[str] = set()
    singleton = {"content-length", "location", "host", "authorization", "proxy-authorization"}
    forbidden_request = {
        "host",
        "connection",
        "proxy-connection",
        "transfer-encoding",
        "content-length",
    }

    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise OutboundHttpEvidenceError("malformed header evidence")
        name, value = _validate_header(item[0], item[1], policy=policy)
        if request and name in forbidden_request:
            raise OutboundHttpPolicyError("transport-owned request header is forbidden")
        if name in singleton:
            if name in seen_singletons:
                raise OutboundHttpEvidenceError("duplicate singleton header")
            seen_singletons.add(name)
        total += len(name.encode("ascii")) + len(value.encode("utf-8")) + 4
        if total > policy.max_total_header_bytes:
            raise OutboundHttpLimitError("total header bytes exceed bound")
        normalized.append((name, value))
    return tuple(normalized)


def _header(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    wanted = name.casefold()
    for key, value in headers:
        if key == wanted:
            return value
    return None


def _content_length(headers: tuple[tuple[str, str], ...]) -> int | None:
    value = _header(headers, "content-length")
    if value is None:
        return None
    if not value or not value.isascii() or not value.isdecimal():
        raise OutboundHttpEvidenceError("invalid Content-Length")
    length = int(value)
    if length < 0:
        raise OutboundHttpEvidenceError("invalid Content-Length")
    return length


def _content_type(headers: tuple[tuple[str, str], ...]) -> str | None:
    value = _header(headers, "content-type")
    if value is None:
        return None
    return _normalize_media_type(value)


def _origin(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    port = parsed.port or 443
    return host, port


def _redirect_target(
    current_url: str,
    headers: tuple[tuple[str, str], ...],
    *,
    policy: OutboundHttpPolicy,
) -> str:
    location = _header(headers, "location")
    if not location:
        raise OutboundHttpEvidenceError("redirect response is missing Location")
    target = urljoin(current_url, location)
    validate_public_https_redirect(
        current_url,
        target,
        allow_cross_origin=policy.allow_cross_origin_redirects,
    )
    return target


async def _bounded_body(
    response: TransportResponse,
    *,
    headers: tuple[tuple[str, str], ...],
    policy: OutboundHttpPolicy,
) -> bytes:
    declared = _content_length(headers)
    if declared is not None and declared > policy.max_response_bytes:
        raise OutboundHttpLimitError("declared response body exceeds byte bound")

    body = bytearray()
    chunks = 0
    try:
        async for raw in response.body:
            chunks += 1
            if chunks > policy.max_response_chunks:
                raise OutboundHttpLimitError("response chunk-count bound exceeded")
            if not isinstance(raw, (bytes, bytearray, memoryview)):
                raise OutboundHttpEvidenceError("response body yielded a non-bytes chunk")
            chunk = bytes(raw)
            if len(body) + len(chunk) > policy.max_response_bytes:
                raise OutboundHttpLimitError("streamed response body exceeds byte bound")
            body.extend(chunk)
    except OutboundHttpError:
        raise
    except Exception as exc:
        raise OutboundHttpEvidenceError("response body stream failed") from exc

    if declared is not None and len(body) != declared:
        raise OutboundHttpEvidenceError("response body length differs from Content-Length")
    return bytes(body)


class SafeAsyncHttpClient:
    """Bounded redirect-aware client over a peer-evidencing transport."""

    def __init__(
        self,
        transport: AsyncOutboundTransport,
        *,
        policy: OutboundHttpPolicy | None = None,
        resolver: Resolver,
    ) -> None:
        if transport is None:
            raise TypeError("transport is required")
        if resolver is None:
            raise TypeError("resolver is required")
        self._transport = transport
        self.policy = policy or OutboundHttpPolicy()
        self._resolver = resolver

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Sequence[tuple[str, str]] | Mapping[str, str] = (),
    ) -> SafeHttpResponse:
        normalized_method = _normalize_method(method)
        if normalized_method not in self.policy.allowed_methods:
            raise OutboundHttpPolicyError("HTTP method is not permitted by policy")
        request_headers = _normalize_headers(headers, policy=self.policy, request=True)

        current = url
        redirects = 0
        while True:
            try:
                destination = resolve_public_https_url(
                    current,
                    purpose="outbound HTTP destination",
                    resolver=self._resolver,
                )
            except ValueError as exc:
                raise OutboundHttpPolicyError("outbound HTTP destination rejected") from exc

            request = TransportRequest(
                method=normalized_method,
                destination=destination,
                headers=request_headers,
                timeout=self.policy.timeout,
            )
            try:
                response = await self._transport.request(request)
            except OutboundHttpError:
                raise
            except Exception as exc:
                raise OutboundHttpEvidenceError("outbound transport failed") from exc

            if (
                isinstance(response.status_code, bool)
                or not isinstance(response.status_code, int)
                or not 100 <= response.status_code <= 599
            ):
                raise OutboundHttpEvidenceError("invalid HTTP status evidence")
            try:
                peer = validate_connected_peer(
                    destination,
                    response.peer_address,
                    purpose="connected HTTP peer",
                )
            except (TypeError, ValueError) as exc:
                raise OutboundHttpEvidenceError("connected peer evidence rejected") from exc

            response_headers = _normalize_headers(
                response.headers,
                policy=self.policy,
                request=False,
            )

            if response.status_code in _REDIRECT_STATUSES:
                if redirects >= self.policy.max_redirects:
                    raise OutboundHttpLimitError("redirect bound exceeded")
                target = _redirect_target(
                    current,
                    response_headers,
                    policy=self.policy,
                )
                # Redirect bodies are deliberately not consumed. The adapter should
                # release/close them as part of its one-hop response lifecycle.
                #
                # Caller-provided headers are authority scoped to the original
                # origin. Even when policy explicitly permits a cross-origin
                # redirect, never forward Authorization, cookies, API keys, or
                # other opaque caller headers to a different origin.
                if _origin(target) != _origin(current):
                    request_headers = ()
                current = target
                redirects += 1
                continue

            media_type = _content_type(response_headers)
            if self.policy.accepted_content_types:
                if media_type is None:
                    raise OutboundHttpPolicyError("response Content-Type is required")
                if media_type not in self.policy.accepted_content_types:
                    raise OutboundHttpPolicyError("response Content-Type is not permitted")

            body = await _bounded_body(
                response,
                headers=response_headers,
                policy=self.policy,
            )
            return SafeHttpResponse(
                url=destination.url,
                status_code=response.status_code,
                headers=response_headers,
                body=body,
                peer_address=peer,
                redirects=redirects,
            )

    async def get(
        self,
        url: str,
        *,
        headers: Sequence[tuple[str, str]] | Mapping[str, str] = (),
    ) -> SafeHttpResponse:
        return await self.request("GET", url, headers=headers)

    async def head(
        self,
        url: str,
        *,
        headers: Sequence[tuple[str, str]] | Mapping[str, str] = (),
    ) -> SafeHttpResponse:
        return await self.request("HEAD", url, headers=headers)


__all__ = [
    "AsyncOutboundTransport",
    "OutboundHttpError",
    "OutboundHttpEvidenceError",
    "OutboundHttpLimitError",
    "OutboundHttpPolicy",
    "OutboundHttpPolicyError",
    "SafeAsyncHttpClient",
    "SafeHttpResponse",
    "TimeoutBudget",
    "TransportRequest",
    "TransportResponse",
]
