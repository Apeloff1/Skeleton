"""Bounded tool / prompt injection fence (issue #807 B082/B086).

Allowlisted verbs only. Fail closed on prompt-injection markers, path
escape, and oversized payloads. No eval, no shell, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.kernel.errors import VaultError


MAX_PAYLOAD_CHARS = 4_096
ALLOWED_TOOLS = frozenset(
    {
        "replay.record",
        "replay.verify",
        "capabilities.list",
        "sota.map",
        "forge.simulate",
    }
)
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system:",
    "<script",
    "```tool",
    "os.system",
    "subprocess",
    "/etc/passwd",
    "../",
    "..\\",
)


class ToolFenceError(VaultError):
    code = "VLT.TOOL_FENCE"
    http_status = 403


@dataclass(frozen=True, slots=True)
class FenceDecision:
    allowed: bool
    tool: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "tool": self.tool, "reason": self.reason}


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(item) for item in value)
    return str(value)


def inspect_tool(tool: str, payload: Mapping[str, Any] | None = None) -> FenceDecision:
    name = str(tool or "").strip().lower()
    if not name:
        raise ToolFenceError("tool name required")
    if name not in ALLOWED_TOOLS:
        raise ToolFenceError(f"tool not on allowlist: {name}")
    blob = _flatten(payload or {})
    if len(blob) > MAX_PAYLOAD_CHARS:
        raise ToolFenceError("payload exceeds fence budget")
    lowered = blob.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            raise ToolFenceError("prompt or path injection marker", context={"marker": marker})
    return FenceDecision(allowed=True, tool=name, reason="allowlist")
