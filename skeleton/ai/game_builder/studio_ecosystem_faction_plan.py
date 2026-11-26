"""Source-leased shortest bounded plans for original faction negotiations.

A plan is an offline counterfactual over authored social rules. It does not
grant earned reputation, mutate a save, or certify a native game outcome.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_faction_reputation import (
    MAX_REPUTATION, MIN_REPUTATION, simulate_faction_reputation,
)
from .studio_ecosystem_quest import StudioQuestError

PLAN_SCHEMA = "skeleton.game_builder.studio_faction_plan.v1"
MAX_PLAN_RULES = 12
MAX_PLAN_DEPTH = 8
MAX_EXPLORED_STATES = 4096


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical faction plan") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _identifier(value: object) -> bool:
    return (type(value) is str and 1 <= len(value) <= 128
            and all(c.isascii() and (c.isalnum() or c in "_-") for c in value))


def plan_faction_negotiation(
    documents: Mapping[str, Any], *, faction_id: str,
    minimum: int | None = None, maximum: int | None = None,
    decisions: list[str] | None = None, expected_source_digest: str | None = None,
    authorized: bool,
) -> dict[str, object]:
    """Find the shortest lexically stable replayable path to an authored goal.

    Exhaustive search is bounded by authored decision count, depth, and states.
    Every transition respects every faction's reputation range; an unreachable
    goal returns an explicit hold, never an invented decision or reward.
    """
    if authorized is not True:
        raise PermissionError("faction planning requires operator authorization")
    if not _identifier(faction_id):
        raise StudioQuestError("invalid faction plan target")
    if ((minimum is None) == (maximum is None)
            or (minimum is not None and
                (type(minimum) is not int or not MIN_REPUTATION <= minimum <= MAX_REPUTATION))
            or (maximum is not None and
                (type(maximum) is not int or not MIN_REPUTATION <= maximum <= MAX_REPUTATION))):
        raise StudioQuestError("exactly one bounded faction reputation threshold required")
    if decisions is None:
        decisions = []
    if type(decisions) is not list:
        raise StudioQuestError("invalid faction decision history")
    # The existing replay validator is the single authority for canonical
    # source, rule shapes, source leases, and repeated/unknown decisions.
    prior = simulate_faction_reputation(
        documents, decisions, authorized=True,
        expected_source_digest=expected_source_digest)
    initial = prior["final_reputation"]
    if faction_id not in initial:
        raise StudioQuestError("unknown authored faction target")
    rules = documents["cast"]["social_rules"]
    remaining = sorted(
        ((rule["decision"], rule["reputation_delta"])
         for rule in rules if rule["decision"] not in decisions),
        key=lambda pair: pair[0],
    )
    if len(remaining) > MAX_PLAN_RULES:
        raise StudioQuestError("faction plan exceeds bounded rule inventory")
    keys = tuple(sorted(initial))
    start = tuple(initial[key] for key in keys)
    target_index = keys.index(faction_id)

    def satisfied(values: tuple[int, ...]) -> bool:
        value = values[target_index]
        return value >= minimum if minimum is not None else value <= maximum

    # BFS guarantees minimum authored decision count; lexical rule order
    # provides deterministic tie-breaking even across Python hash seeds.
    queue = deque([(0, start, ())])
    visited = {(0, start)}
    selected: tuple[str, ...] | None = None
    explored = 0
    while queue:
        mask, values, path = queue.popleft()
        explored += 1
        if explored > MAX_EXPLORED_STATES:
            raise StudioQuestError("faction plan state budget exceeded")
        if satisfied(values):
            selected = path
            break
        if len(path) == MAX_PLAN_DEPTH:
            continue
        for index, (name, deltas) in enumerate(remaining):
            bit = 1 << index
            if mask & bit:
                continue
            following = tuple(values[position] + deltas[key]
                              for position, key in enumerate(keys))
            if any(not MIN_REPUTATION <= value <= MAX_REPUTATION
                   for value in following):
                continue
            next_mask = mask | bit
            marker = (next_mask, following)
            if marker not in visited:
                visited.add(marker)
                queue.append((next_mask, following, path + (name,)))

    result = prior
    if selected is not None:
        # Re-run the complete canonical engine, not an independent
        # authority, to prove the counterfactual result and source identity.
        result = simulate_faction_reputation(
            documents, decisions + list(selected), authorized=True,
            expected_source_digest=prior["source_digest"])
        if result["initial_reputation"] != prior["initial_reputation"]:
            raise StudioQuestError("faction plan replay source mismatch")
        if not satisfied(tuple(result["final_reputation"][key] for key in keys)):
            raise StudioQuestError("faction plan replay failed target")
    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "project_id": prior["project_id"],
        "source_digest": prior["source_digest"],
        "rules_digest": prior["rules_digest"],
        "faction_id": faction_id,
        "threshold": {"minimum": minimum} if minimum is not None else {"maximum": maximum},
        "history_decisions": list(decisions),
        "history_digest": prior["reputation_digest"],
        "starting_reputation": initial,
        "planned_decisions": list(selected or ()),
        "planned_decision_count": len(selected or ()),
        "resulting_reputation": result["final_reputation"],
        "resulting_replay_digest": result["reputation_digest"],
        "explored_states": explored,
        "status": "simulatable" if selected is not None else "unreachable_within_budget",
        "source_unchanged": True,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["plan_digest"] = _digest(payload)
    return payload
