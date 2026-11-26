"""Source-bound combat objectives with deterministic reward and checkpoint custody.

Objectives only observe the canonical combat campaign; they cannot modify its
currency, combat outcomes or hero statistics. Every awarded point is recomputed
from the original authored source and the canonical combat replay.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    MAX_CURRENCY, advance_campaign, new_campaign, normalize_campaign,
    original_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_objectives.v1"
SAVE_SCHEMA = "skeleton.combat_objectives_save.v1"
PACKAGE_SCHEMA = "skeleton.combat_objectives_package.v1"
MAX_OBJECTIVES = 16
MAX_POINTS = 10000
MAX_TOTAL_POINTS = 100000
KINDS = frozenset({"victory", "survive", "currency", "final_victory"})


def _encoded(value: Any) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise CombatSessionError("invalid objectives JSON") from exc
    if len(text.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError("objectives payload exceeds 128 KiB")
    return text


def normalize_objectives(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "campaign", "objectives"},
                  "objectives source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported objectives schema")
    campaign = normalize_campaign(obj["campaign"])
    entries = obj["objectives"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_OBJECTIVES:
        raise CombatSessionError("invalid objectives count")
    encounter_order = {
        entry["scenario"]["encounter_id"]: index
        for index, entry in enumerate(campaign["encounters"])
    }
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    total = 0
    for raw_entry in entries:
        item = _object(raw_entry, {
            "objective_id", "encounter_id", "kind", "threshold",
            "points", "requires",
        }, "objective")
        objective_id = _id(item["objective_id"], "objective_id")
        encounter_id = _id(item["encounter_id"], "encounter_id")
        if objective_id in ids:
            raise CombatSessionError("duplicate objective identity")
        if encounter_id not in encounter_order:
            raise CombatSessionError("objective references unknown encounter")
        kind = item["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise CombatSessionError("unsupported objective kind")
        threshold = _integer(item["threshold"], "threshold", 0, MAX_CURRENCY)
        if kind in ("victory", "final_victory") and threshold != 0:
            raise CombatSessionError("boolean objective threshold must be zero")
        if kind == "survive" and not 1 <= threshold <= 10000:
            raise CombatSessionError("survival threshold out of bounds")
        if (kind == "final_victory"
                and encounter_order[encounter_id] != len(encounter_order) - 1):
            raise CombatSessionError("final victory must target last encounter")
        points = _integer(item["points"], "points", 1, MAX_POINTS)
        total += points
        if total > MAX_TOTAL_POINTS:
            raise CombatSessionError("objective points budget exceeded")
        dependencies = item["requires"]
        if type(dependencies) is not list or len(dependencies) > MAX_OBJECTIVES:
            raise CombatSessionError("invalid objective dependencies")
        if len(set(str(value) for value in dependencies)) != len(dependencies):
            raise CombatSessionError("duplicate objective dependency")
        checked: list[str] = []
        for value in dependencies:
            dep_id = _id(value, "required objective")
            dependency = by_id.get(dep_id)
            if dependency is None:
                raise CombatSessionError("objective requires unknown or forward dependency")
            if (encounter_order[dependency["encounter_id"]]
                    >= encounter_order[encounter_id]):
                raise CombatSessionError("objective dependency must precede encounter")
            checked.append(dep_id)
        item_out = {
            "objective_id": objective_id, "encounter_id": encounter_id,
            "kind": kind, "threshold": threshold, "points": points,
            "requires": checked,
        }
        ids.add(objective_id)
        by_id[objective_id] = item_out
        normalized.append(item_out)
    result = {"schema_version": SCHEMA, "campaign": campaign,
              "objectives": normalized}
    _encoded(result)
    return result


def _checkpoint(source: dict[str, Any], campaign: dict[str, Any],
                state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": SAVE_SCHEMA,
        "source_digest": dig(source),
        "state_digest": dig(state),
        "campaign_save_digest": dig(campaign["save"]),
        "parent_digest": dig(parent) if parent is not None else None,
        "tick": len(state["journal"]),
    }


def _snapshot(source: dict[str, Any], campaign: dict[str, Any],
              state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "campaign_session": campaign,
        "state": state, "state_digest": dig(state),
        "save": _checkpoint(source, campaign, state, parent),
    }
    _encoded(result)
    return result


def new_objectives(source: Any) -> dict[str, Any]:
    spec = normalize_objectives(source)
    campaign = new_campaign(spec["campaign"])
    state = {"phase": "active", "score": 0, "journal": []}
    return _snapshot(spec, campaign, state, None)


def _condition(contract: dict[str, Any], campaign: dict[str, Any]) -> bool:
    state = campaign["state"]
    latest = state["encounters"][-1]
    combat = latest["combat"]["state"]
    won = (combat["phase"] == "won"
           and combat["winner"] == campaign["source"]["hero_team"])
    kind = contract["kind"]
    if kind == "victory":
        return won
    if kind == "survive":
        return won and state["hero_hp"] >= contract["threshold"]
    if kind == "currency":
        return won and state["currency"] >= contract["threshold"]
    return state["phase"] == "won"


def _advance(snapshot: dict[str, Any]) -> dict[str, Any]:
    before = snapshot["campaign_session"]
    if before["state"]["phase"] != "active":
        raise CombatSessionError("objectives campaign already terminal")
    after = advance_campaign(before)
    index = before["state"]["next_index"]
    encounter_id = snapshot["source"]["campaign"]["encounters"][index]["scenario"]["encounter_id"]
    prior_status = {
        outcome["objective_id"]: outcome["status"]
        for entry in snapshot["state"]["journal"] for outcome in entry["outcomes"]
    }
    outcomes: list[dict[str, Any]] = []
    points = 0
    for objective in snapshot["source"]["objectives"]:
        if objective["encounter_id"] != encounter_id:
            continue
        prerequisites = all(prior_status.get(key) == "completed"
                            for key in objective["requires"])
        passed = prerequisites and _condition(objective, after)
        status = ("blocked" if not prerequisites else
                  "completed" if passed else "failed")
        awarded = objective["points"] if passed else 0
        points += awarded
        outcomes.append({
            "objective_id": objective["objective_id"],
            "status": status, "points": awarded,
        })
    score = snapshot["state"]["score"] + points
    if score > MAX_TOTAL_POINTS:
        raise CombatSessionError("objective score overflow")
    entry = {
        "encounter_id": encounter_id,
        "combat_digest": dig(after["state"]["encounters"][-1]["combat"]),
        "outcomes": outcomes, "score_after": score,
    }
    state = {
        "phase": after["state"]["phase"], "score": score,
        "journal": [*snapshot["state"]["journal"], entry],
    }
    return _snapshot(snapshot["source"], after, state, snapshot["save"])


def verify_objectives(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "campaign_session",
        "state", "state_digest", "save",
    }, "objectives session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported objectives save schema")
    _encoded(obj)
    journal = obj["state"].get("journal") if type(obj["state"]) is dict else None
    if type(journal) is not list:
        raise CombatSessionError("invalid objectives journal")
    rebuilt = new_objectives(obj["source"])
    if len(journal) > len(rebuilt["source"]["campaign"]["encounters"]):
        raise CombatSessionError("objectives journal exceeds encounter count")
    for _ in journal:
        rebuilt = _advance(rebuilt)
    if rebuilt != obj:
        raise CombatSessionError("objectives replay or save lineage mismatch")
    return rebuilt


def advance_objectives(raw: Any) -> dict[str, Any]:
    return _advance(verify_objectives(raw))


def finish_objectives(source: Any, *, resume: Any = None) -> dict[str, Any]:
    normalized = normalize_objectives(source)
    result = new_objectives(normalized) if resume is None else verify_objectives(resume)
    if result["source_digest"] != dig(normalized):
        raise CombatSessionError("objectives resume source mismatch")
    while result["state"]["phase"] == "active":
        result = _advance(result)
    return verify_objectives(result)


def objective_summary(raw: Any) -> dict[str, Any]:
    snapshot = verify_objectives(raw)
    observed = {
        item["objective_id"]: item
        for entry in snapshot["state"]["journal"] for item in entry["outcomes"]
    }
    statuses = []
    for item in snapshot["source"]["objectives"]:
        outcome = observed.get(item["objective_id"])
        status = (outcome["status"] if outcome is not None else
                  "pending" if snapshot["state"]["phase"] == "active" else "unreachable")
        statuses.append({"objective_id": item["objective_id"], "status": status,
                         "points": outcome["points"] if outcome is not None else 0})
    return {
        "schema_version": SCHEMA, "source_digest": snapshot["source_digest"],
        "state_digest": snapshot["state_digest"],
        "phase": snapshot["state"]["phase"], "score": snapshot["state"]["score"],
        "objectives": statuses,
    }


def package_objectives(raw: Any) -> dict[str, Any]:
    snapshot = verify_objectives(raw)
    manifest = {
        "source_digest": snapshot["source_digest"],
        "state_digest": snapshot["state_digest"],
        "campaign_save_digest": dig(snapshot["campaign_session"]["save"]),
        "phase": snapshot["state"]["phase"], "score": snapshot["state"]["score"],
        "completed_encounters": len(snapshot["state"]["journal"]),
    }
    result = {"schema_version": PACKAGE_SCHEMA, "manifest": manifest,
              "snapshot": snapshot}
    result["digest"] = dig(result)
    _encoded(result)
    return result


def verify_objectives_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "manifest", "snapshot", "digest"},
                  "objectives package")
    if obj["schema_version"] != PACKAGE_SCHEMA:
        raise CombatSessionError("unsupported objectives package schema")
    _encoded(obj)
    expected = package_objectives(obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("objectives package integrity or replay mismatch")
    return expected


def original_objectives() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "campaign": original_campaign(),
        "objectives": [
            {"objective_id": "clear_reeds", "encounter_id": "reed_watch",
             "kind": "victory", "threshold": 0, "points": 10, "requires": []},
            {"objective_id": "guard_lantern", "encounter_id": "tide_gate",
             "kind": "survive", "threshold": 1, "points": 20,
             "requires": ["clear_reeds"]},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-objectives")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play and export original objective campaign")
    start = sub.add_parser("start")
    start.add_argument("--source-json", required=True)
    for command in ("advance", "verify", "finish", "summary", "pack"):
        action = sub.add_parser(command)
        action.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = package_objectives(finish_objectives(original_objectives()))
        elif args.command == "start":
            result = new_objectives(_parse_json(args.source_json, "objectives source"))
        elif args.command == "unpack":
            result = verify_objectives_package(_parse_json(args.package_json, "objectives package"))
        else:
            saved = _parse_json(args.session_json, "objectives session")
            if args.command == "advance":
                result = advance_objectives(saved)
            elif args.command == "verify":
                result = verify_objectives(saved)
            elif args.command == "finish":
                result = finish_objectives(saved["source"], resume=saved)
            elif args.command == "summary":
                result = objective_summary(saved)
            else:
                result = package_objectives(saved)
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
