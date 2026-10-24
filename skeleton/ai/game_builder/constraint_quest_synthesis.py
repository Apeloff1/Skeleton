"""Constraint-guided quest synthesis (#807 B037).

Generated quests must pass reachability, prerequisite, reward and content-policy
validation before acceptance. Synthesis is deterministic (seeded) and every
candidate goes through ``validate_quest``; anything that fails is rejected
(fail closed). B035 (narrative planner/canon graph) is not on main yet, so the
world/canon input is a plain location graph + allowed-content policy that B035
can supply later.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_ID = "ai.quest_synthesis.v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class WorldModel:
    start: str
    edges: Mapping[str, tuple[str, ...]]  # location -> neighbours
    npcs: Mapping[str, str] = field(default_factory=dict)  # npc -> location

    def reachable(self) -> set[str]:
        seen, stack = {self.start}, [self.start]
        while stack:
            for nxt in self.edges.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen


@dataclass(frozen=True, slots=True)
class ContentPolicy:
    banned_terms: tuple[str, ...] = ()
    max_reward_per_step: int = 100
    max_total_reward: int = 500
    allowed_reward_kinds: tuple[str, ...] = ("xp", "gold", "item")


def validate_quest(quest: Mapping[str, Any], world: WorldModel, policy: ContentPolicy) -> list[str]:
    """Return a list of violations; empty means the quest is acceptable."""
    errors: list[str] = []
    steps = quest.get("steps")
    if not isinstance(steps, list) or not steps:
        return ["quest has no steps"]
    reachable = world.reachable()
    ids = [s.get("id") for s in steps]
    if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
        errors.append("step ids must be unique non-empty strings")
    seen: set[str] = set()
    total = 0
    for step in steps:
        sid = step.get("id")
        loc = step.get("location")
        if loc not in reachable:
            errors.append(f"{sid}: location {loc!r} unreachable")
        npc = step.get("npc")
        if npc is not None and world.npcs.get(npc) not in reachable:
            errors.append(f"{sid}: npc {npc!r} unreachable")
        for req in step.get("requires", ()):
            if req not in seen:
                errors.append(f"{sid}: prerequisite {req!r} not satisfied by an earlier step")
        for reward in step.get("rewards", ()):
            kind, amount = reward.get("kind"), reward.get("amount", 0)
            if kind not in policy.allowed_reward_kinds:
                errors.append(f"{sid}: reward kind {kind!r} not allowed")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                errors.append(f"{sid}: invalid reward amount")
                continue
            if amount > policy.max_reward_per_step:
                errors.append(f"{sid}: reward exceeds per-step cap")
            total += amount
        text = f"{quest.get('title', '')} {step.get('text', '')}".lower()
        for term in policy.banned_terms:
            if term.lower() in text:
                errors.append(f"{sid}: content policy violation ({term})")
        if isinstance(sid, str):
            seen.add(sid)
    if total > policy.max_total_reward:
        errors.append("total reward exceeds cap")
    return errors


def synthesize_quest(
    world: WorldModel,
    policy: ContentPolicy,
    *,
    seed: int,
    length: int = 3,
    title: str = "Errand",
    max_attempts: int = 16,
) -> dict[str, Any]:
    """Seeded generate-and-validate. Returns accepted quest or a rejection record."""
    if length < 1 or max_attempts < 1:
        raise ValueError("length and max_attempts must be positive")
    rng = random.Random(seed)
    locations = sorted(world.reachable())
    npcs_at = {}
    for npc, loc in sorted(world.npcs.items()):
        npcs_at.setdefault(loc, []).append(npc)
    last_errors: list[str] = []
    for attempt in range(max_attempts):
        steps = []
        for i in range(length):
            loc = rng.choice(locations)
            npc = rng.choice(npcs_at[loc]) if npcs_at.get(loc) else None
            amount = rng.randint(1, policy.max_reward_per_step)
            steps.append({
                "id": f"s{i}",
                "location": loc,
                "npc": npc,
                "requires": [f"s{i-1}"] if i else [],
                "rewards": [{"kind": rng.choice(policy.allowed_reward_kinds), "amount": amount}],
                "text": f"Go to {loc}" + (f" and speak with {npc}" if npc else ""),
            })
        quest = {"title": title, "seed": seed, "steps": steps}
        last_errors = validate_quest(quest, world, policy)
        if not last_errors:
            body = {"schema": SCHEMA_ID, "accepted": True, "attempt": attempt, "quest": quest}
            return {**body, "digest": _digest(body)}
    body = {"schema": SCHEMA_ID, "accepted": False, "attempt": max_attempts, "errors": last_errors}
    return {**body, "digest": _digest(body)}


__all__ = ["SCHEMA_ID", "ContentPolicy", "WorldModel", "synthesize_quest", "validate_quest"]
