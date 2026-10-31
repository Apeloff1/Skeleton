"""Deterministic source-bound faction reputation consequences for original worlds.

This models authored social-rule effects, not real-world approval, game-engine
currency, or earned narrative evidence. It never mutates the registered cast.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError

REPUTATION_SCHEMA = "skeleton.game_builder.studio_faction_reputation.v1"
MAX_FACTIONS = 32
MAX_RULES = 64
MAX_DECISIONS = 32
MIN_REPUTATION = -100
MAX_REPUTATION = 100


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical faction reputation input") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _identifier(value: object) -> bool:
    return (type(value) is str and 1 <= len(value) <= 128
            and all(c.isascii() and (c.isalnum() or c in "_-") for c in value))


def simulate_faction_reputation(
    documents: Mapping[str, Any], decisions: list[str], *,
    authorized: bool, expected_source_digest: str | None = None,
) -> dict[str, object]:
    """Replay a bounded list of unique authored decisions with exact receipts."""
    if authorized is not True:
        raise PermissionError("faction reputation requires operator authorization")
    if (type(decisions) is not list or len(decisions) > MAX_DECISIONS
            or any(not _identifier(d) for d in decisions)
            or len(set(decisions)) != len(decisions)):
        raise StudioQuestError("invalid or repeated faction decision")
    if not isinstance(documents, Mapping):
        raise StudioQuestError("missing authored faction source")
    original = _canonical(documents)
    if len(original) > 512 * 1024:
        raise StudioQuestError("faction source exceeds byte budget")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("faction source contradicts authored canon")
    if (expected_source_digest is not None
            and (type(expected_source_digest) is not str
                 or expected_source_digest != proof["source_digest"])):
        raise StudioQuestError("stale faction source digest")
    cast = documents.get("cast")
    if type(cast) is not dict:
        raise StudioQuestError("missing authored cast")
    factions = cast.get("factions")
    rules = cast.get("social_rules")
    if (type(factions) is not list or not 1 <= len(factions) <= MAX_FACTIONS
            or type(rules) is not list or not 1 <= len(rules) <= MAX_RULES):
        raise StudioQuestError("invalid faction or social-rule inventory")
    state: dict[str, int] = {}
    for faction in factions:
        if (type(faction) is not dict or not _identifier(faction.get("id"))
                or type(faction.get("reputation")) is not int
                or not MIN_REPUTATION <= faction["reputation"] <= MAX_REPUTATION
                or faction["id"] in state):
            raise StudioQuestError("invalid or repeated faction record")
        state[faction["id"]] = faction["reputation"]
    table: dict[str, dict[str, int]] = {}
    for rule in rules:
        if type(rule) is not dict or not _identifier(rule.get("decision")):
            raise StudioQuestError("invalid faction social rule")
        decision = rule["decision"]
        delta = rule.get("reputation_delta")
        if (decision in table or type(delta) is not dict
                or set(delta) != set(state)
                or any(type(v) is not int or not -10 <= v <= 10
                       for v in delta.values())):
            raise StudioQuestError("invalid faction social-rule deltas")
        table[decision] = delta
    initial = dict(sorted(state.items()))
    steps: list[dict[str, object]] = []
    for index, decision in enumerate(decisions):
        if decision not in table:
            raise StudioQuestError("unknown authored faction decision")
        before = _digest(state)
        updated = {key: state[key] + table[decision][key] for key in sorted(state)}
        if any(not MIN_REPUTATION <= value <= MAX_REPUTATION
               for value in updated.values()):
            raise StudioQuestError("faction reputation would exceed bounded range")
        state = updated
        steps.append({
            "index": index, "decision": decision,
            "before_digest": before, "after_digest": _digest(state),
            "delta": dict(sorted(table[decision].items())),
        })
    if _canonical(documents) != original:
        raise StudioQuestError("faction source changed during replay")
    payload: dict[str, object] = {
        "schema": REPUTATION_SCHEMA,
        "project_id": proof["project_id"],
        "source_digest": proof["source_digest"],
        "rules_digest": _digest(rules),
        "initial_reputation": initial,
        "final_reputation": dict(sorted(state.items())),
        "steps": steps,
        "decision_count": len(steps),
        "original_source_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["reputation_digest"] = _digest(payload)
    return payload
