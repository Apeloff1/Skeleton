"""Context rot guard — detect attention dilution before it degrades output.

Direction-B research (production → frontier, 2026): every frontier model
degrades as input length grows — constraints buried mid-context get
silently dropped ("attention dilution"). The fix that production teams
converged on is not bigger windows; it's *monitoring position*: track
where critical constraints sit in the context and how much separates
them from the live edge, and flag rot before the model answers.

This guard scores a composed prompt for rot risk:

- **Burial** — critical constraints (marked or matched) sitting far from
  the end of the context, where attention is weakest.
- **Dilution** — raw length: total tokens over the attention budget.
- **Repetition decay** — a constraint stated once early and never
  restated is effectively dropped; restated constraints score better.

Pure domain — no model call. Compose with ``memory/compaction.py``:
compact when the guard says rot risk is high.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from skeleton.memory.prefix_renderer import estimate_tokens


@dataclass(frozen=True)
class RotReport:
    """Rot assessment for one composed context."""
    total_tokens: int
    risk: float                        # 0 fresh .. 1 rotten
    burial_score: float                # mean distance of constraints from the edge
    dilution_score: float              # length over attention budget
    restated: int                      # constraints stated more than once
    buried: List[str]                  # constraint ids sitting in the dead zone
    verdict: str                       # fresh | watch | rot

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "risk": round(self.risk, 4),
            "burial_score": round(self.burial_score, 4),
            "dilution_score": round(self.dilution_score, 4),
            "restated": self.restated,
            "buried": list(self.buried),
            "verdict": self.verdict,
        }


class ContextRotGuard:
    """Score a composed prompt for context-rot risk.

    ``attention_budget``: tokens past which dilution begins to hurt
    (default 32k — the 2026 reports show degradation well inside advertised
    windows). ``dead_zone``: fraction of the context (from the start) where
    a constraint stated once is considered buried (default first 60%).
    """

    def __init__(self, *, attention_budget: int = 32_000,
                 dead_zone: float = 0.6, watch_at: float = 0.4,
                 rot_at: float = 0.65) -> None:
        self.attention_budget = attention_budget
        self.dead_zone = dead_zone
        self.watch_at = watch_at
        self.rot_at = rot_at
        self.checks = 0
        self.rot_events = 0

    def assess(self, prompt: str, *,
               constraints: Optional[Sequence[str]] = None) -> RotReport:
        """Score the prompt. ``constraints`` are literal strings the answer
        must respect; when omitted, ALL-CAPS / numbered-rule lines are
        auto-detected as constraints."""
        self.checks += 1
        total_tokens = estimate_tokens(prompt)
        lines = prompt.splitlines()
        lengths = [estimate_tokens(l) for l in lines]
        offsets: List[int] = []
        running = 0
        for n in lengths:
            offsets.append(running)
            running += n

        if constraints is None:
            constraints = tuple(
                l.strip() for l in lines
                if l.strip() and (l.strip().isupper() or re.match(r"^\s*\d+[.)]", l))
            )

        # locate constraints; count restatements
        positions: Dict[str, List[float]] = {}
        for c in constraints:
            if not c:
                continue
            for i, line in enumerate(lines):
                if c in line:
                    pos = (offsets[i] / total_tokens) if total_tokens else 0.0
                    positions.setdefault(c, []).append(pos)

        buried: List[str] = []
        restated = 0
        burial_scores: List[float] = []
        for c, poses in positions.items():
            earliest = min(poses)
            if len(poses) > 1:
                restated += 1
            elif earliest < self.dead_zone:
                buried.append(c[:40])
                burial_scores.append(1.0 - earliest)

        burial = (sum(burial_scores) / len(burial_scores)) if burial_scores else 0.0
        dilution = min(1.0, total_tokens / max(1, self.attention_budget))
        risk = 0.55 * dilution + 0.35 * burial + 0.10 * (
            1.0 if restated == 0 and positions else 0.0
        )
        verdict = "rot" if risk >= self.rot_at else (
            "watch" if risk >= self.watch_at else "fresh"
        )
        if verdict == "rot":
            self.rot_events += 1
        return RotReport(
            total_tokens=total_tokens, risk=risk, burial_score=burial,
            dilution_score=dilution, restated=restated, buried=buried,
            verdict=verdict,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "checks": self.checks,
            "rot_events": self.rot_events,
            "rot_rate": round(self.rot_events / max(1, self.checks), 4),
        }
