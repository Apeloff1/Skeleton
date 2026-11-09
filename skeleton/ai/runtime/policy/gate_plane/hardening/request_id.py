"""Request-id, W3C trace context and hop propagation across s2s and bus hops.

Every inbound s2s call (and every agent-edge bus envelope) carries:

* ``x-request-id`` — opaque correlation id, 8-128 chars of ``[A-Za-z0-9._:-]``.
  Accepted from the caller when well formed, otherwise regenerated (never
  echoed back unvalidated, so it cannot be used for header/log injection).
* ``traceparent`` — W3C Trace Context ``00-<trace-id>-<parent-id>-<flags>``.
  Each hop keeps the ``trace-id`` and mints a fresh ``parent-id`` (span id).
* ``x-s2s-hop`` — hop counter; a call arriving with ``hop >= max_hops`` is
  rejected as a probable routing loop (``508 Loop Detected``).
* ``x-s2s-via`` — comma-separated service chain (bounded), used to detect a
  service seeing its own name again (a cycle) and for audit trails.

The helpers are transport-neutral: they read/write plain ``Mapping[str, str]``
so the same code serves HTTP headers, ASGI scopes and bus envelope headers
(adapters only; nothing in ``agent_edge`` or ``api/server.py`` is edited).
The current :class:`RequestContext` lives in a :mod:`contextvars` slot so
outbound clients inside a handler propagate automatically.
"""

from __future__ import annotations

import contextvars
import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterator, List, Mapping, MutableMapping, Optional, Tuple

REQUEST_ID_HEADER = "x-request-id"
TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"
HOP_HEADER = "x-s2s-hop"
VIA_HEADER = "x-s2s-via"
DEFAULT_MAX_HOPS = 16
MAX_VIA_ENTRIES = 32
MAX_TRACESTATE_LEN = 512

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_TRACEPARENT_RE = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_VIA_ENTRY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,62}$")
_ZERO_TRACE = "0" * 32
_ZERO_SPAN = "0" * 16

IdFactory = Callable[[], str]


class HopLimitExceeded(Exception):
    """Raised when a call arrives with too many hops or a service cycle."""

    status = 508
    reason = "loop_detected"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def new_request_id() -> str:
    return "req-" + secrets.token_hex(12)


def new_trace_id() -> str:
    while True:
        tid = secrets.token_hex(16)
        if tid != _ZERO_TRACE:
            return tid


def new_span_id() -> str:
    while True:
        sid = secrets.token_hex(8)
        if sid != _ZERO_SPAN:
            return sid


def valid_request_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_REQUEST_ID_RE.match(value))


@dataclass(frozen=True)
class TraceParent:
    trace_id: str
    span_id: str
    flags: str = "01"
    version: str = "00"

    @classmethod
    def parse(cls, raw: Optional[str]) -> Optional["TraceParent"]:
        """Parse a ``traceparent`` header; ``None`` when absent or invalid."""
        if not isinstance(raw, str):
            return None
        m = _TRACEPARENT_RE.match(raw.strip().lower())
        if not m:
            return None
        version, trace_id, span_id, flags = m.groups()
        if version == "ff" or trace_id == _ZERO_TRACE or span_id == _ZERO_SPAN:
            return None
        return cls(trace_id=trace_id, span_id=span_id, flags=flags, version="00")

    @classmethod
    def fresh(cls, *, sampled: bool = True) -> "TraceParent":
        return cls(trace_id=new_trace_id(), span_id=new_span_id(), flags="01" if sampled else "00")

    def child(self) -> "TraceParent":
        return replace(self, span_id=new_span_id())

    @property
    def sampled(self) -> bool:
        return bool(int(self.flags, 16) & 0x01)

    def header(self) -> str:
        return f"{self.version}-{self.trace_id}-{self.span_id}-{self.flags}"


@dataclass(frozen=True)
class RequestContext:
    """Correlation state for one request as it crosses services and bus hops."""

    request_id: str
    trace: TraceParent
    hop: int = 0
    via: Tuple[str, ...] = ()
    tracestate: Optional[str] = None
    origin: str = "generated"  # generated | inbound
    baggage: Mapping[str, str] = field(default_factory=dict)

    @property
    def trace_id(self) -> str:
        return self.trace.trace_id

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "trace_id": self.trace.trace_id,
            "span_id": self.trace.span_id,
            "sampled": self.trace.sampled,
            "hop": self.hop,
            "via": list(self.via),
            "origin": self.origin,
        }

    def outbound_headers(self, service: Optional[str] = None) -> Dict[str, str]:
        """Headers for the *next* hop: same request id/trace, new span, hop+1."""
        via = list(self.via)
        if service:
            via.append(service)
        via = via[-MAX_VIA_ENTRIES:]
        out = {
            REQUEST_ID_HEADER: self.request_id,
            TRACEPARENT_HEADER: self.trace.child().header(),
            HOP_HEADER: str(self.hop + 1),
        }
        if via:
            out[VIA_HEADER] = ",".join(via)
        if self.tracestate:
            out[TRACESTATE_HEADER] = self.tracestate
        return out


def _lower(headers: Mapping[str, Any]) -> Dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def _parse_hop(raw: Optional[str]) -> int:
    if raw is None:
        return 0
    raw = raw.strip()
    if not raw.isdigit() or len(raw) > 4:
        return 0
    return int(raw)


def _parse_via(raw: Optional[str]) -> Tuple[str, ...]:
    if not raw:
        return ()
    entries: List[str] = []
    for part in raw.split(","):
        p = part.strip().lower()
        if p and _VIA_ENTRY_RE.match(p):
            entries.append(p)
    return tuple(entries[-MAX_VIA_ENTRIES:])


def _clean_tracestate(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) > MAX_TRACESTATE_LEN or any(ord(c) < 0x20 or ord(c) > 0x7E for c in raw):
        return None
    return raw


@dataclass(frozen=True)
class PropagationPolicy:
    """How inbound correlation headers are trusted."""

    max_hops: int = DEFAULT_MAX_HOPS
    trust_inbound_request_id: bool = True
    trust_inbound_trace: bool = True
    reject_cycles: bool = True
    id_factory: Optional[IdFactory] = None

    def __post_init__(self) -> None:
        if not 1 <= self.max_hops <= 255:
            raise ValueError("max_hops must be within [1, 255]")


def extract_context(
    headers: Mapping[str, Any],
    *,
    service: Optional[str] = None,
    policy: Optional[PropagationPolicy] = None,
) -> RequestContext:
    """Build the :class:`RequestContext` for an inbound call.

    Raises :class:`HopLimitExceeded` when the hop counter is at the limit or
    (with ``reject_cycles``) when ``service`` already appears in ``via``.
    """
    pol = policy or PropagationPolicy()
    low = _lower(headers)
    hop = _parse_hop(low.get(HOP_HEADER))
    via = _parse_via(low.get(VIA_HEADER))
    if hop >= pol.max_hops:
        raise HopLimitExceeded(f"hop {hop} >= max_hops {pol.max_hops}")
    if pol.reject_cycles and service and service in via:
        raise HopLimitExceeded(f"service {service!r} already in via chain")
    rid_raw = low.get(REQUEST_ID_HEADER)
    origin = "generated"
    if pol.trust_inbound_request_id and valid_request_id(rid_raw):
        request_id = str(rid_raw)
        origin = "inbound"
    else:
        request_id = (pol.id_factory or new_request_id)()
    trace = TraceParent.parse(low.get(TRACEPARENT_HEADER)) if pol.trust_inbound_trace else None
    tracestate = _clean_tracestate(low.get(TRACESTATE_HEADER)) if trace is not None else None
    if trace is None:
        trace = TraceParent.fresh()
    else:
        trace = trace.child()
    return RequestContext(
        request_id=request_id, trace=trace, hop=hop, via=via, tracestate=tracestate, origin=origin
    )


_CURRENT: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar(
    "gate_plane_request_context", default=None
)


def current_context() -> Optional[RequestContext]:
    return _CURRENT.get()


@contextmanager
def bind_context(ctx: RequestContext) -> Iterator[RequestContext]:
    token = _CURRENT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT.reset(token)


def propagate(
    headers: Optional[Mapping[str, str]] = None,
    *,
    service: Optional[str] = None,
    ctx: Optional[RequestContext] = None,
) -> Dict[str, str]:
    """Return ``headers`` plus correlation headers for an outbound hop.

    Uses ``ctx`` or the bound :func:`current_context`; with neither, a fresh
    root context is started so every outbound call is still traceable.
    Existing correlation headers in ``headers`` are overwritten (the bound
    context is authoritative).
    """
    base = dict(headers or {})
    context = ctx or current_context()
    if context is None:
        context = RequestContext(request_id=new_request_id(), trace=TraceParent.fresh())
    for key in list(base):
        if key.lower() in (REQUEST_ID_HEADER, TRACEPARENT_HEADER, HOP_HEADER, VIA_HEADER, TRACESTATE_HEADER):
            del base[key]
    base.update(context.outbound_headers(service))
    return base


def envelope_headers(envelope_headers_in: Optional[Mapping[str, str]], *, service: str) -> Dict[str, str]:
    """Bus-hop adapter: correlation headers to stamp on an outgoing bus envelope.

    Reads the inbound envelope's headers (if this publish is a reaction to a
    consumed message) so request id and trace survive agent→bus→agent hops.
    """
    if envelope_headers_in:
        inbound = extract_context(envelope_headers_in, policy=PropagationPolicy(reject_cycles=False))
        return inbound.outbound_headers(service)
    ctx = current_context()
    if ctx is not None:
        return ctx.outbound_headers(service)
    return RequestContext(request_id=new_request_id(), trace=TraceParent.fresh()).outbound_headers(service)


def stamp_asgi_scope(scope: MutableMapping[str, Any], ctx: RequestContext) -> None:
    state = scope.setdefault("state", {})
    if isinstance(state, dict):
        state["request_context"] = ctx
    scope["request_context"] = ctx


def response_headers(ctx: RequestContext) -> List[Tuple[str, str]]:
    return [(REQUEST_ID_HEADER, ctx.request_id), (TRACEPARENT_HEADER, ctx.trace.header())]


class RequestIdStage:
    """Pipeline stage (kind ``telemetry``) stamping correlation headers on calls.

    Outermost slot so retries of the same logical call share one request id
    while each attempt gets a fresh span id; the bound context is recorded in
    ``ctx.attrs['request_context']``.
    """

    kind = "telemetry"

    def __init__(self, *, service: Optional[str] = None, name: str = "request_id") -> None:
        self.name = name
        self.service = service

    def invoke(self, request: Any, ctx: Any, nxt: Callable[[Any, Any], Any]) -> Any:
        from skeleton.gate_plane.pipeline.core import PipelineRequest

        low = _lower(request.headers)
        bound = current_context()
        if bound is None and valid_request_id(low.get(REQUEST_ID_HEADER)):
            bound = extract_context(request.headers, policy=PropagationPolicy(reject_cycles=False))
        if bound is None:
            bound = RequestContext(request_id=new_request_id(), trace=TraceParent.fresh())
        ctx.attrs["request_context"] = bound.as_dict()
        stamped = PipelineRequest(
            method=request.method,
            path=request.path,
            headers=propagate(request.headers, service=self.service or request.service, ctx=bound),
            body=request.body,
            tenant_id=request.tenant_id,
            priority=request.priority,
            service=request.service,
        )
        ctx.event("request_id", request_id=bound.request_id, trace_id=bound.trace_id)
        return nxt(stamped, ctx)


__all__ = [
    "DEFAULT_MAX_HOPS",
    "HOP_HEADER",
    "HopLimitExceeded",
    "PropagationPolicy",
    "REQUEST_ID_HEADER",
    "RequestContext",
    "RequestIdStage",
    "TRACEPARENT_HEADER",
    "TRACESTATE_HEADER",
    "TraceParent",
    "VIA_HEADER",
    "bind_context",
    "current_context",
    "envelope_headers",
    "extract_context",
    "new_request_id",
    "new_span_id",
    "new_trace_id",
    "propagate",
    "response_headers",
    "stamp_asgi_scope",
    "valid_request_id",
]
