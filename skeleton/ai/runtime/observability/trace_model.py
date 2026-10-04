"""Immutable trace evidence contracts layered over runtime tracing.

The existing distributed tracer remains the collection mechanism. This module
adds stable cross-boundary identity, causal links, and sanitized snapshots for
evidence correlation. Trace evidence is never authoritative runtime state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Mapping

from skeleton.observability.distributed_tracing import Span


_HEX_RE = re.compile(r"^[0-9a-f]{16,64}$")
_SENSITIVE_KEYS = frozenset({
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "prompt",
    "user_content",
})
_SENSITIVE_SUFFIXES = (
    "_credential",
    "_credentials",
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
    "_prompt",
    "_content",
)


class TraceModelError(ValueError):
    """A trace identity, link, or evidence invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceModelError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise TraceModelError(f"{name} exceeds maximum length")
    return value


def _trace_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or not _HEX_RE.fullmatch(value):
        raise TraceModelError(f"{name} must be lowercase hexadecimal trace identity")
    return value


def _ns(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceModelError(f"{name} must be a non-negative integer")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TraceModelError("trace evidence must be canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def _safe_scalar(name: str, value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 1024:
            raise TraceModelError(f"{name} exceeds maximum value length")
        if isinstance(value, float) and not math.isfinite(value):
            raise TraceModelError(f"{name} must be finite")
        return value
    raise TraceModelError(f"{name} must be a JSON scalar")


def sanitize_trace_attributes(
    attributes: Mapping[str, object],
) -> tuple[tuple[str, str | int | float | bool | None], ...]:
    """Return canonical non-sensitive scalar attributes only."""

    if not isinstance(attributes, Mapping):
        raise TraceModelError("trace attributes must be a mapping")
    rows: list[tuple[str, str | int | float | bool | None]] = []
    for key, value in attributes.items():
        clean_key = _token("attribute key", key)
        if _is_sensitive_key(clean_key):
            raise TraceModelError(
                f"sensitive trace attribute is forbidden:{clean_key}"
            )
        rows.append(
            (
                clean_key,
                _safe_scalar(f"attribute {clean_key}", value),
            )
        )
    return tuple(sorted(rows))


@dataclass(frozen=True, slots=True)
class TraceId:
    """Stable operation/correlation identity suitable for propagation."""

    trace_id: str
    operation_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _trace_hex("trace_id", self.trace_id))
        object.__setattr__(
            self,
            "operation_id",
            _token("operation_id", self.operation_id),
        )
        object.__setattr__(
            self,
            "correlation_id",
            _token("correlation_id", self.correlation_id),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "trace_id": self.trace_id,
                "operation_id": self.operation_id,
                "correlation_id": self.correlation_id,
            }
        )


@dataclass(frozen=True, slots=True)
class TraceLink:
    """Directed causal link between two spans in the same trace."""

    trace_id: str
    parent_span_id: str
    child_span_id: str
    relation: str = "parent"

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _trace_hex("trace_id", self.trace_id))
        object.__setattr__(
            self,
            "parent_span_id",
            _trace_hex("parent_span_id", self.parent_span_id),
        )
        object.__setattr__(
            self,
            "child_span_id",
            _trace_hex("child_span_id", self.child_span_id),
        )
        object.__setattr__(self, "relation", _token("relation", self.relation))
        if self.parent_span_id == self.child_span_id:
            raise TraceModelError("trace link cannot self-reference")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "trace_id": self.trace_id,
                "parent_span_id": self.parent_span_id,
                "child_span_id": self.child_span_id,
                "relation": self.relation,
            }
        )


@dataclass(frozen=True, slots=True)
class SpanEvidence:
    """Immutable sanitized snapshot of one collected runtime span."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: tuple[tuple[str, str | int | float | bool | None], ...]
    telemetry_authoritative: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _trace_hex("trace_id", self.trace_id))
        object.__setattr__(self, "span_id", _trace_hex("span_id", self.span_id))
        if self.parent_span_id is not None:
            object.__setattr__(
                self,
                "parent_span_id",
                _trace_hex("parent_span_id", self.parent_span_id),
            )
            if self.parent_span_id == self.span_id:
                raise TraceModelError("span cannot be its own parent")
        object.__setattr__(self, "name", _token("name", self.name))
        object.__setattr__(self, "start_ns", _ns("start_ns", self.start_ns))
        object.__setattr__(self, "end_ns", _ns("end_ns", self.end_ns))
        if self.end_ns < self.start_ns:
            raise TraceModelError("span end cannot predate span start")
        if not isinstance(self.attributes, tuple):
            raise TraceModelError("attributes must be an immutable tuple")
        keys = [
            item[0]
            for item in self.attributes
            if isinstance(item, tuple) and len(item) == 2
        ]
        if len(keys) != len(self.attributes):
            raise TraceModelError("attributes must contain key/value pairs")
        if len(keys) != len(set(keys)):
            raise TraceModelError("trace attribute keys must be unique")
        canonical = sanitize_trace_attributes(dict(self.attributes))
        object.__setattr__(self, "attributes", canonical)
        if self.telemetry_authoritative is not False:
            raise TraceModelError("trace telemetry cannot be authoritative state")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "trace_id": self.trace_id,
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "name": self.name,
                "start_ns": self.start_ns,
                "end_ns": self.end_ns,
                "attributes": [[key, value] for key, value in self.attributes],
                "telemetry_authoritative": False,
            }
        )


def snapshot_span(span: Span) -> SpanEvidence:
    """Convert a finished runtime span into sanitized immutable evidence."""

    if not isinstance(span, Span):
        raise TypeError("span must be distributed_tracing.Span")
    if span.end_ns is None:
        raise TraceModelError("unfinished span cannot become trace evidence")
    if not isinstance(span.start_ns, int) or not isinstance(span.end_ns, int):
        raise TraceModelError("runtime span timestamps must be integer nanoseconds")
    return SpanEvidence(
        trace_id=span.context.trace_id,
        span_id=span.context.span_id,
        parent_span_id=span.context.parent_id,
        name=span.name,
        start_ns=span.start_ns,
        end_ns=span.end_ns,
        attributes=sanitize_trace_attributes(span.tags),
    )


def causal_link_for(span: SpanEvidence) -> TraceLink | None:
    """Build the parent link for a span snapshot when a parent exists."""

    if not isinstance(span, SpanEvidence):
        raise TypeError("span must be SpanEvidence")
    if span.parent_span_id is None:
        return None
    return TraceLink(
        trace_id=span.trace_id,
        parent_span_id=span.parent_span_id,
        child_span_id=span.span_id,
    )


__all__ = [
    "SpanEvidence",
    "TraceId",
    "TraceLink",
    "TraceModelError",
    "causal_link_for",
    "sanitize_trace_attributes",
    "snapshot_span",
]
