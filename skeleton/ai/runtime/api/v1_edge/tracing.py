"""W3C traceparent propagation and request-id assignment."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Optional

_TP = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_RID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    parent_id: Optional[str]
    span_id: str
    sampled: bool

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{'01' if self.sampled else '00'}"


def parse_or_start(traceparent: Optional[str]) -> TraceContext:
    span = secrets.token_hex(8)
    if traceparent:
        m = _TP.match(traceparent.strip().lower())
        if m and m.group(1) != "0" * 32 and m.group(2) != "0" * 16:
            return TraceContext(m.group(1), m.group(2), span, int(m.group(3), 16) & 1 == 1)
    return TraceContext(secrets.token_hex(16), None, span, True)


def request_id(incoming: Optional[str]) -> str:
    if incoming and _RID.match(incoming):
        return incoming
    return secrets.token_hex(12)
