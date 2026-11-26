"""Replay-derived, source-authored mission DAG with mutually exclusive earned endings."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from .custody import canonical, digest
from .engine import apply, initial_state
from .journal import verify_journal
from .schema import parse_world, world_dict

SCHEMA = "ridge.rescue.missions.v1"
REVISION = "ridge.rescue.missions.revision.v1"
EXPORT = "ridge.rescue.missions.export.v1"
MAX_NODES = 64
MAX_SOURCE = 128_000
MAX_EXPORT = 512_000
ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
CONDITIONS = {"event", "rescued", "enemy_defeated", "beacon", "shelter", "ending"}


class MissionError(ValueError):
    pass


def _decode(value: Any, limit: int) -> dict:
    if isinstance(value, bytes):
        if len(value) > limit:
            raise MissionError("mission document too large")
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MissionError("mission document is not UTF-8") from exc
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limit:
            raise MissionError("mission document too large")
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise MissionError("invalid mission JSON") from exc
    if not isinstance(value, dict) or len(canonical(value)) > limit:
        raise MissionError("invalid or oversized mission document")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise MissionError(f"invalid {label}")
    return value


def _title(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 96 or any(ord(c) < 32 for c in value):
        raise MissionError("invalid mission title")
    return value


def parse_missions(source: dict | str | bytes) -> dict:
    data = _decode(source, MAX_SOURCE)
    if set(data) != {"schema", "id", "title", "world", "nodes"} or data["schema"] != SCHEMA:
        raise MissionError("invalid mission source contract")
    try:
        world = parse_world(data["world"])
    except (ValueError, TypeError, KeyError) as exc:
        raise MissionError("invalid mission world") from exc
    nodes = data["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise MissionError("invalid mission node count")
    seen: set[str] = set()
    total = 0
    normalized = []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "title", "requires", "condition", "points", "group"}:
            raise MissionError("invalid mission node")
        ident = _id(node["id"], "mission id")
        if ident in seen:
            raise MissionError("duplicate mission id")
        dependencies = node["requires"]
        if not isinstance(dependencies, list) or len(dependencies) > MAX_NODES or any(not isinstance(v, str) or v not in seen for v in dependencies):
            raise MissionError("dependencies must refer to preceding nodes")
        if len(set(dependencies)) != len(dependencies):
            raise MissionError("duplicate mission dependency")
        condition = node["condition"]
        if not isinstance(condition, dict) or set(condition) != {"kind", "value"}:
            raise MissionError("invalid mission condition")
        kind, value = condition["kind"], condition["value"]
        if not isinstance(kind, str) or kind not in CONDITIONS:
            raise MissionError("unsupported mission condition")
        if kind in {"beacon", "shelter"}:
            if value is not True:
                raise MissionError("boolean mission condition must be true")
        elif not isinstance(value, str) or not 1 <= len(value) <= 64 or not value.isascii() or any(ord(c) < 32 for c in value):
            raise MissionError("invalid mission condition value")
        if kind == "rescued" and value not in {i for i, _ in world.civilians}:
            raise MissionError("unknown mission civilian")
        if kind == "enemy_defeated" and value not in {i for i, _ in world.raiders}:
            raise MissionError("unknown mission enemy")
        if kind == "ending" and value not in {"won:protect", "won:salvage"}:
            raise MissionError("invalid mission ending")
        points = node["points"]
        if type(points) is not int or not 0 <= points <= 100:
            raise MissionError("invalid mission points")
        total += points
        if total > 1000:
            raise MissionError("mission reward budget exceeded")
        group = node["group"]
        if group != "":
            _id(group, "mission group")
        normalized.append({"id": ident, "title": _title(node["title"]),
                           "requires": list(dependencies), "condition": {"kind": kind, "value": value},
                           "points": points, "group": group})
        seen.add(ident)
    result = {"schema": SCHEMA, "id": _id(data["id"], "source id"), "title": _title(data["title"]),
              "world": world_dict(world), "nodes": normalized}
    if len(canonical(result)) > MAX_SOURCE:
        raise MissionError("mission source exceeds byte budget")
    return result


def _holds(condition: dict, state: dict, world) -> bool:
    kind, value = condition["kind"], condition["value"]
    if kind == "event":
        return any(event.startswith(value) for event in state["events"])
    if kind == "rescued":
        return state["civilians"][value] == "rescued"
    if kind == "enemy_defeated":
        return state["raiders"][value]["health"] == 0
    if kind == "beacon":
        return state["flags"]["beacon"]
    if kind == "shelter":
        return tuple(state["position"]) == world.shelter
    return state["status"] == value


def evaluate_missions(source: dict | str | bytes, journal: dict | str | bytes) -> dict:
    missions = parse_missions(source)
    try:
        verified = verify_journal(journal)
    except (ValueError, TypeError, KeyError) as exc:
        raise MissionError("unreplayable mission journal") from exc
    world = verified["world"]
    if canonical(world_dict(world)) != canonical(missions["world"]):
        raise MissionError("journal source does not match mission world")
    # Replay each prefix to derive first-earned turn. No client-supplied badges.
    state = initial_state(world)
    earned: dict[str, int] = {}
    chosen: dict[str, str] = {}
    for turn in range(len(verified["actions"]) + 1):
        for node in missions["nodes"]:
            ident = node["id"]
            group = node["group"]
            if ident in earned or any(req not in earned for req in node["requires"]):
                continue
            if group and group in chosen:
                continue
            if _holds(node["condition"], state, world):
                earned[ident] = turn
                if group:
                    chosen[group] = ident
        if turn < len(verified["actions"]):
            state = apply(world, state, verified["actions"][turn])
    report = [{"id": node["id"], "earned": node["id"] in earned,
               "first_turn": earned.get(node["id"]), "points": node["points"] if node["id"] in earned else 0,
               "group": node["group"]} for node in missions["nodes"]]
    return {"schema": "ridge.rescue.missions.report.v1", "source_sha256": digest(missions),
            "journal_head": verify_journal(journal)["head"], "turn": state["turn"],
            "status": state["status"], "score": sum(node["points"] for node in report),
            "earned": report, "chosen": chosen}


def revise_missions(source: dict, *, expected_sha256: str, operation: dict) -> dict:
    before = parse_missions(source)
    if expected_sha256 != digest(before):
        raise MissionError("stale mission source revision")
    if not isinstance(operation, dict) or set(operation) != {"kind", "id", "value"}:
        raise MissionError("invalid mission edit operation")
    if operation["kind"] not in {"set-title", "set-points", "set-condition", "set-requires"}:
        raise MissionError("unsupported mission edit")
    result = deepcopy(before)
    matches = [node for node in result["nodes"] if node["id"] == operation["id"]]
    if len(matches) != 1:
        raise MissionError("unknown mission edit target")
    key = {"set-title": "title", "set-points": "points", "set-condition": "condition",
           "set-requires": "requires"}[operation["kind"]]
    matches[0][key] = deepcopy(operation["value"])
    updated = parse_missions(result)
    return {"schema": REVISION, "previous_sha256": expected_sha256,
            "sha256": digest(updated), "source": updated}


def verify_revision(before: dict, revision: dict, operation: dict) -> bool:
    if not isinstance(revision, dict) or set(revision) != {"schema", "previous_sha256", "sha256", "source"} or revision["schema"] != REVISION:
        raise MissionError("invalid mission revision")
    expected = revise_missions(before, expected_sha256=digest(parse_missions(before)), operation=operation)
    if canonical(expected) != canonical(revision):
        raise MissionError("mission revision does not replay")
    return True


def export_missions(source: dict, journal: dict) -> dict:
    parsed = parse_missions(source)
    report = evaluate_missions(parsed, journal)
    payload = {"schema": EXPORT, "source": parsed, "journal": journal, "report": report}
    bundle = {"payload": payload, "sha256": digest(payload)}
    if len(canonical(bundle)) > MAX_EXPORT:
        raise MissionError("mission export exceeds byte budget")
    return bundle


def verify_export(value: dict | str | bytes) -> dict:
    bundle = _decode(value, MAX_EXPORT)
    if set(bundle) != {"payload", "sha256"} or not isinstance(bundle["payload"], dict):
        raise MissionError("invalid mission export")
    payload = bundle["payload"]
    if set(payload) != {"schema", "source", "journal", "report"} or payload["schema"] != EXPORT:
        raise MissionError("invalid mission export payload")
    if digest(payload) != bundle["sha256"]:
        raise MissionError("mission export digest mismatch")
    expected = evaluate_missions(payload["source"], payload["journal"])
    if canonical(expected) != canonical(payload["report"]):
        raise MissionError("mission report not earned by replay")
    return expected
