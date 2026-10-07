"""Guarded compaction — drop history only when a required constraint survives.

Turns that state a constraint are kept whole. Optional turns fill the
remaining token budget from the head and the tail. A constraint is never
reported as preserved unless its exact text is still in a kept turn, and a
required turn that does not fit the budget fails the compaction instead of
being sliced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from skeleton.memory.prefix_renderer import estimate_tokens
from skeleton.memory.compaction import ContextCompactor, Turn
from skeleton.memory.rot_guard import ContextRotGuard, RotReport


class CompactionError(ValueError):
    """The history cannot be compacted without dropping a required constraint."""


def compact_turns(
    turns: list[dict[str, Any]] | None,
    constraints: list[str] | None = None,
    *,
    token_budget: int = 8_000,
) -> dict[str, Any] | None:
    if turns is None:
        return None
    if not isinstance(turns, list):
        raise TypeError("turns must be a list")
    if not turns:
        return None
    if constraints is None:
        constraints = []
    if not isinstance(constraints, list) or any(not isinstance(item, str) or not item for item in constraints):
        raise ValueError("constraints must be non-empty strings")
    if isinstance(token_budget, bool) or not isinstance(token_budget, int) or token_budget < 1:
        raise ValueError("token_budget must be a positive integer")

    normalized: list[dict[str, Any]] = []
    roles: dict[str, int] = {}
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise TypeError("each turn must be an object")
        role = turn.get("role")
        content = turn.get("content")
        if not isinstance(role, str) or not role.strip() or role != role.strip():
            raise ValueError("turn role must be a non-empty string")
        if not isinstance(content, str):
            raise ValueError("turn content must be a string")
        roles[role] = roles.get(role, 0) + 1
        normalized.append({
            "index": index,
            "role": role,
            "content": content,
            "tokens": estimate_tokens(content),
        })

    required_indexes: set[int] = set()
    unmet: list[str] = []
    for constraint in constraints:
        hits = [turn["index"] for turn in normalized if constraint in turn["content"]]
        if not hits:
            unmet.append(constraint)
            continue
        required_indexes.update(hits)

    required = [turn for turn in normalized if turn["index"] in required_indexes]
    required_tokens = sum(turn["tokens"] for turn in required)
    if required_tokens > token_budget:
        raise CompactionError("constraint turns exceed the token budget")

    optional = [turn for turn in normalized if turn["index"] not in required_indexes]
    remaining = token_budget - required_tokens
    head: list[dict[str, Any]] = []
    used = 0
    head_budget = remaining // 2
    for turn in optional:
        if turn["tokens"] > remaining - used:
            break
        if head and used >= head_budget:
            break
        head.append(turn)
        used += turn["tokens"]

    kept_ids = {turn["index"] for turn in head}
    tail: list[dict[str, Any]] = []
    tail_used = 0
    tail_budget = remaining - used
    for turn in reversed(optional):
        if turn["index"] in kept_ids:
            continue
        if turn["tokens"] > tail_budget - tail_used:
            break
        tail.append(turn)
        tail_used += turn["tokens"]
    tail.reverse()

    kept = sorted(required + head + tail, key=lambda turn: turn["index"])
    kept_ids = {turn["index"] for turn in kept}
    dropped = [turn["index"] for turn in normalized if turn["index"] not in kept_ids]
    preserved_constraints = [constraint for constraint in constraints if constraint not in unmet]
    for constraint in preserved_constraints:
        if not any(constraint in turn["content"] for turn in kept):
            raise CompactionError(f"constraint was dropped: {constraint}")

    report = ContextRotGuard().assess(
        "\n".join(turn["content"] for turn in kept), constraints=constraints
    )
    return {
        "original_count": len(normalized),
        "preserved_count": len(kept),
        "middle_summarized": len(dropped),
        "role_distribution": roles,
        "preserved_turns": [
            {"index": turn["index"], "role": turn["role"], "content": turn["content"]}
            for turn in kept
        ],
        "constraints_preserved": preserved_constraints,
        "constraints_unmet": unmet,
        "dropped_indexes": dropped,
        "kept_tokens": sum(turn["tokens"] for turn in kept),
        "token_budget": token_budget,
        "turns": [{"role": turn["role"], "content": turn["content"]} for turn in kept],
        "compacted": bool(dropped),
        "verdict": report.verdict,
        "report": report.to_dict(),
    }


def turns_from_payload(payload: Any) -> list[Turn]:
    """Read valid turns from optional legacy payloads without coercing content."""
    if not isinstance(payload, list):
        return []
    return [
        Turn(role=item["role"], content=item["content"])
        for item in payload
        if isinstance(item, dict)
        and isinstance(item.get("role"), str)
        and bool(item["role"].strip())
        and item["role"] == item["role"].strip()
        and isinstance(item.get("content"), str)
    ]


@dataclass(frozen=True)
class GuardedCompactionResult:
    turns: list[Turn]
    compacted: bool
    report: RotReport
    hint: str | None


class RotGuardedCompactor:
    """Compose rot assessment with whole-turn, constraint-preserving trimming.

    The supplied compactor provides the budget. Selection uses compact_turns
    so a legacy head/tail strategy cannot silently discard required evidence.
    """

    def __init__(self, *, guard: ContextRotGuard | None = None,
                 compactor: ContextCompactor | None = None) -> None:
        self.guard = guard or ContextRotGuard()
        self.compactor = compactor or ContextCompactor()
        self._checks = 0
        self._interventions = 0

    def process(self, turns: list[Turn], *,
                constraints: Sequence[str] | None = None) -> GuardedCompactionResult:
        if not isinstance(turns, list) or any(not isinstance(turn, Turn) for turn in turns):
            raise TypeError("turns must be a list of Turn objects")
        if constraints is not None and (not isinstance(constraints, (list, tuple))
                or any(not isinstance(item, str) or not item for item in constraints)):
            raise ValueError("constraints must be a sequence of nonempty strings")
        if any(not isinstance(turn.role, str) or not turn.role.strip()
               or turn.role != turn.role.strip() or not isinstance(turn.content, str) for turn in turns):
            raise ValueError("turns require a nonempty role and string content")
        constraints = list(constraints) if constraints is not None else None
        report = self.guard.assess("\n".join(turn.content for turn in turns), constraints=constraints)
        self._checks += 1
        hint = "restate missing or buried constraints explicitly" if report.buried else None
        if report.verdict != "rot" and sum(turn.tokens for turn in turns) <= self.compactor.token_budget:
            return GuardedCompactionResult(list(turns), False, report, hint)
        result = compact_turns(
            [{"role": turn.role, "content": turn.content} for turn in turns],
            constraints, token_budget=self.compactor.token_budget,
        )
        if result is None:
            return GuardedCompactionResult([], False, report, hint)
        kept = turns_from_payload(result["turns"])
        compacted = result["compacted"]
        self._interventions += int(compacted)
        final_report = self.guard.assess("\n".join(turn.content for turn in kept), constraints=constraints)
        return GuardedCompactionResult(kept, compacted, final_report, hint)

    def stats(self) -> dict[str, int]:
        return {"checks": self._checks, "interventions": self._interventions}


__all__ = ["CompactionError", "compact_turns", "RotGuardedCompactor",
           "GuardedCompactionResult", "turns_from_payload"]
