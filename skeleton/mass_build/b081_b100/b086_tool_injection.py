"""B086: untrusted data cannot silently escalate agent tool permissions.

Taint tracking: every tool request carries the provenance of the text that
triggered it; requests whose permission exceeds the session baseline and
originate from untrusted content are denied and recorded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ._core import ContractError, require, verdict

LEVELS = ("read", "write", "exec", "admin")
OVERRIDE = re.compile(r"(?i)(ignore (all|previous) instructions|you are now|system prompt|grant yourself)")


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    level: str
    source: str  # "user" | "policy" | "untrusted"
    text: str = ""

    def __post_init__(self) -> None:
        require(self.level in LEVELS, f"bad level {self.level}")
        require(self.source in ("user", "policy", "untrusted"), f"bad source {self.source}")


class Mediator:
    def __init__(self, baseline: str) -> None:
        require(baseline in LEVELS, "bad baseline")
        self.baseline = baseline
        self.audit: list[str] = []

    def decide(self, r: ToolRequest) -> bool:
        escalates = LEVELS.index(r.level) > LEVELS.index(self.baseline)
        injected = bool(OVERRIDE.search(r.text))
        allow = not (r.source == "untrusted" and (escalates or injected))
        if r.source != "untrusted" and escalates:
            allow = r.source == "user"
        self.audit.append(f"{r.tool}:{r.level}:{r.source}:{'allow' if allow else 'deny'}")
        return allow


def evaluate(baseline: str, attacks: list[ToolRequest]):
    m = Mediator(baseline)
    findings = [f"escalated:{a.tool}:{a.level}" for a in attacks if m.decide(a)]
    return verdict("B086", findings, attacks=len(attacks), audit=len(m.audit))
