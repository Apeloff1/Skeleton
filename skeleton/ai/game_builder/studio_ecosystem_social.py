"""Deterministic, replayable authored-faction reputation, not real social proof."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .studio_ecosystem_quest import StudioQuestError


def _hash(v: object) -> str:
    return sha256(json.dumps(v, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class FactionProgram:
    project_id: str
    source_digest: str
    factions: tuple[tuple[str, int], ...]
    decisions: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]


def compile_factions(documents: Mapping[str, Any]) -> FactionProgram:
    cast = documents.get("cast")
    if not isinstance(cast, dict) or cast.get("release_certified") is not False:
        raise StudioQuestError("missing, unqualified authored cast")
    pid = cast.get("project_id")
    if not isinstance(pid, str) or not pid:
        raise StudioQuestError("invalid cast identity")
    raw = cast.get("factions")
    if not isinstance(raw, list) or not raw:
        raise StudioQuestError("missing authored factions")
    initial: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise StudioQuestError("invalid faction")
        key, rep = item.get("id"), item.get("reputation")
        if (not isinstance(key, str) or not key or key in initial or
                type(rep) is not int):
            raise StudioQuestError("invalid faction identity or initial reputation")
        initial[key] = rep
    schema_fields = ("dialogue_branches", "social_effects", "social_rules")
    present = [key for key in schema_fields if key in cast]
    if len(present) != 1:
        raise StudioQuestError("ambiguous or missing reputation rules")
    effects = cast[present[0]]
    if not isinstance(effects, list) or not effects:
        raise StudioQuestError("missing social choices")
    decisions: dict[str, tuple[tuple[str, int], ...]] = {}
    for item in effects:
        if not isinstance(item, dict):
            raise StudioQuestError("invalid social choice")
        label = item.get("decision" if present[0] == "social_rules" else "choice")
        delta = (item.get("reputation_delta") if present[0] != "social_effects"
                 else {f: item.get(f) for f in initial})
        if (not isinstance(label, str) or not label or label in decisions or
                not isinstance(delta, dict) or not delta or
                not set(delta).issubset(initial) or
                any(type(amount) is not int for amount in delta.values())):
            raise StudioQuestError("invalid authored reputation effect")
        decisions[label] = tuple(sorted(delta.items()))
    return FactionProgram(pid, _hash(cast), tuple(sorted(initial.items())),
                          tuple(sorted(decisions.items())))


def replay_factions(documents: Mapping[str, Any], decisions: Sequence[str],
                    *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("reputation replay requires operator authorization")
    program = compile_factions(documents)
    if not isinstance(decisions, (list, tuple)) or len(decisions) > 4096:
        raise StudioQuestError("invalid social replay budget")
    state = dict(program.factions)
    rules = {key: dict(deltas) for key, deltas in program.decisions}
    history = []
    prev = program.source_digest
    for decision in decisions:
        if not isinstance(decision, str) or decision not in rules:
            raise StudioQuestError("non-authored social decision")
        for faction, delta in rules[decision].items():
            state[faction] += delta
        event = {"previous_digest": prev, "decision": decision,
                 "reputation": dict(sorted(state.items()))}
        prev = _hash(event)
        history.append({"decision": decision, "digest": prev})
    return {
        "schema": "skeleton.game_builder.studio_faction_replay.v1",
        "project_id": program.project_id, "source_digest": program.source_digest,
        "reputation": dict(sorted(state.items())), "events": history,
        "replay_digest": prev, "social_events_real_world_verified": False,
        "release_certified": False,
    }
