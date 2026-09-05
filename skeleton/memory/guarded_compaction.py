"""Rot-triggered compaction — the context-rot loop, closed.

``ContextRotGuard`` detects attention dilution; ``ContextCompactor`` trims.
This module composes them: assess the running turn list, and only compact
when the guard says the context is rotting — never earlier (over-eager
compaction loses information for no gain) and never later.

The loop per call:

1. Render turns to prompt text and assess rot.
2. verdict == "fresh" → return turns untouched.
3. verdict == "watch" → return turns untouched, report the warning.
4. verdict == "rot"   → compact (head + marker + tail), report the repair.

Restating-buried-constraints is reported back to the caller as a hint —
the cheapest rot fix is often restating the rule near the live edge, not
compacting at all.

Pure domain; deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .compaction import CompactionResult, ContextCompactor, Turn
from .rot_guard import ContextRotGuard, RotReport


@dataclass
class GuardedResult:
    turns: List[Turn]
    report: RotReport
    compacted: bool
    hint: Optional[str]              # cheapest available repair, if any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compacted": self.compacted,
            "turns": len(self.turns),
            "hint": self.hint,
            "report": self.report.to_dict(),
        }


class RotGuardedCompactor:
    """Guard + compactor: compact exactly when rot demands it."""

    def __init__(self, *, guard: Optional[ContextRotGuard] = None,
                 compactor: Optional[ContextCompactor] = None) -> None:
        self.guard = guard or ContextRotGuard()
        self.compactor = compactor or ContextCompactor()
        self.interventions = 0

    @staticmethod
    def _render(turns: Sequence[Turn]) -> str:
        return "\n".join(f"{t.role}: {t.content}" for t in turns)

    def process(self, turns: List[Turn], *,
                constraints: Optional[Sequence[str]] = None) -> GuardedResult:
        report = self.guard.assess(self._render(turns), constraints=constraints)

        hint = None
        if report.buried:
            hint = ("restate buried constraints near the live edge: "
                    + ", ".join(report.buried[:3]))

        if report.verdict != "rot":
            return GuardedResult(turns=list(turns), report=report,
                                 compacted=False, hint=hint)

        out: CompactionResult = self.compactor.compact(turns)
        self.interventions += 1
        return GuardedResult(turns=out.turns, report=report,
                             compacted=True, hint=hint)

    def stats(self) -> Dict[str, Any]:
        return {
            "interventions": self.interventions,
            "guard": self.guard.stats(),
            "compactions": self.compactor.compactions,
        }


def turns_from_payload(raw: Any) -> List[Turn]:
    """Coerce API/request ``turns`` payloads into ``Turn`` objects.

    Accepts a list of ``{role, content}`` dicts. Malformed entries are
    skipped. Empty / non-list input yields ``[]`` so callers can gate
    on truthiness.
    """
    if not isinstance(raw, list):
        return []
    out: List[Turn] = []
    for item in raw:
        if isinstance(item, Turn):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if content is None:
            continue
        role = str(item.get("role") or "user")
        out.append(Turn(role=role, content=str(content)))
    return out


def compact_turns(
    raw_turns: Any,
    *,
    constraints: Optional[Sequence[str]] = None,
    compactor: Optional["RotGuardedCompactor"] = None,
) -> Optional[Dict[str, Any]]:
    """Run rot-triggered compaction when turns are present.

    Returns ``None`` when no usable turns were supplied (caller leaves
    the response shape unchanged). Otherwise a dict ready for the API
    ``compaction`` field.
    """
    turns = turns_from_payload(raw_turns)
    if not turns:
        return None
    gc = compactor or RotGuardedCompactor()
    guarded = gc.process(turns, constraints=constraints)
    return {
        "compacted": guarded.compacted,
        "verdict": guarded.report.verdict,
        "hint": guarded.hint,
        "report": guarded.report.to_dict(),
        "turns": [{"role": t.role, "content": t.content} for t in guarded.turns],
    }

