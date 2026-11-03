"""Transactional tactics policy editing with CAS and deterministic preview."""
from __future__ import annotations
from copy import deepcopy

from .custody import canonical, digest
from .tactics import TacticsError, parse_policy, suggest
from .journal import open_journal
from .schema import World

SCHEMA = "ridge.rescue.tactics.revision.v1"


def revise_policy(world: World, source: dict | str | bytes, operation: dict) -> dict:
    before = parse_policy(source)
    if not isinstance(operation, dict) or set(operation) != {"expected_sha256", "field", "value"}:
        raise TacticsError("invalid policy edit")
    if operation["expected_sha256"] != digest(before):
        raise TacticsError("stale tactics source revision")
    if operation["field"] not in {"title", "objective", "risk", "prefer_crafting", "max_steps"}:
        raise TacticsError("unsupported policy edit")
    after = deepcopy(before)
    after[operation["field"]] = operation["value"]
    after = parse_policy(after)
    preview = suggest(world, open_journal(world), after)
    if not preview["ranked"]:
        raise TacticsError("edited tactics policy cannot make an initial move")
    return {"schema": SCHEMA, "previous_sha256": digest(before),
            "sha256": digest(after), "policy": after,
            "preview_action": preview["ranked"][0]["action"]}


def verify_policy_revision(world: World, source: dict | str | bytes, operation: dict, revision: dict) -> bool:
    if not isinstance(revision, dict) or set(revision) != {
        "schema", "previous_sha256", "sha256", "policy", "preview_action"
    } or revision["schema"] != SCHEMA:
        raise TacticsError("invalid policy revision")
    expected = revise_policy(world, source, operation)
    if canonical(expected) != canonical(revision):
        raise TacticsError("policy revision did not replay")
    return True
