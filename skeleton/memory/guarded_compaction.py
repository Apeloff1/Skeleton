"""Guarded compaction — drop history only when a required constraint survives.

Turns that state a constraint are kept whole. Optional turns fill the
remaining token budget from the head and the tail. A constraint is never
reported as preserved unless its exact text is still in a kept turn, and a
required turn that does not fit the budget fails the compaction instead of
being sliced.
"""

from __future__ import annotations

from typing import Any

from skeleton.memory.prefix_renderer import estimate_tokens


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
    }


__all__ = ["CompactionError", "compact_turns"]
