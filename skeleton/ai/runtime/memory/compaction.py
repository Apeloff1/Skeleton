"""Context compaction — head/tail trimming with a token budget.

Wave-3 SOTA (2026 context-engineering guides; the head/tail pattern):
when a turn history nears the window limit, keep the *task context* (head)
and the *recent work* (tail), and replace the dropped middle with a
compaction marker carrying a one-line summary. Unlike plain sliding
windows, nothing is silently lost: the marker preserves what was dropped
in one sentence, and the head anchors the original task.

Budget split: 20% head (task framing) / 80% tail (recent turns) by default,
matching the pattern now standard in agent runtimes.

Pure domain; turns are dicts with ``role`` and ``content`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.memory.prefix_renderer import estimate_tokens


@dataclass(frozen=True)
class Turn:
    role: str
    content: str

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


@dataclass
class CompactionResult:
    turns: List[Turn]
    compacted: bool
    dropped_turns: int
    dropped_tokens: int
    marker: Optional[str]

    def total_tokens(self) -> int:
        return sum(t.tokens for t in self.turns)


def _summarize(turns: List[Turn]) -> str:
    """One-line summary of the dropped middle: first words of each role run."""
    parts = []
    for t in turns[:3]:
        snippet = " ".join(t.content.split()[:8])
        parts.append(f"{t.role}: {snippet}")
    more = f" (+{len(turns) - 3} more)" if len(turns) > 3 else ""
    return " | ".join(parts) + more


class ContextCompactor:
    """Head/tail context trimming against a token budget."""

    def __init__(self, *, token_budget: int = 8_000,
                 head_ratio: float = 0.2) -> None:
        if not 0.0 < head_ratio < 1.0:
            raise ValueError("head_ratio must be in (0, 1)")
        self.token_budget = token_budget
        self.head_ratio = head_ratio
        self.compactions = 0

    def compact(self, turns: List[Turn]) -> CompactionResult:
        """Return turns that fit the budget: head + marker + tail."""
        total = sum(t.tokens for t in turns)
        if total <= self.token_budget:
            return CompactionResult(
                turns=list(turns), compacted=False,
                dropped_turns=0, dropped_tokens=0, marker=None,
            )

        head_budget = int(self.token_budget * self.head_ratio)
        tail_budget = self.token_budget - head_budget

        head: List[Turn] = []
        used = 0
        for t in turns:
            if used + t.tokens > head_budget:
                break
            head.append(t)
            used += t.tokens

        tail: List[Turn] = []
        used = 0
        for t in reversed(turns):
            if used + t.tokens > tail_budget:
                break
            tail.append(t)
            used += t.tokens
        tail.reverse()

        kept_ids = {id(t) for t in head} | {id(t) for t in tail}
        middle = [t for t in turns if id(t) not in kept_ids]
        dropped_tokens = sum(t.tokens for t in middle)

        marker = None
        if middle:
            marker = f"[compacted {len(middle)} turns — {_summarize(middle)}]"

        out = list(head)
        if marker:
            out.append(Turn(role="system", content=marker))
        out.extend(tail)
        self.compactions += 1
        return CompactionResult(
            turns=out, compacted=True,
            dropped_turns=len(middle), dropped_tokens=dropped_tokens,
            marker=marker,
        )
