"""Original multi-stage survival campaigns with earned, replay-bound progression.

Each stage runs the canonical tile survival engine. A campaign cannot award a
stage reward without a verified winning terminal state; saves and portable
exports are rebuilt from the complete action journal, not trusted snapshots.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_survival import (
    _action as survival_action, _advance as survival_advance,
    _json, export_survival, new_survival, normalize_survival,
    original_survival,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_survival_campaign.v1"
BUNDLE = "skeleton.scene_survival_campaign_bundle.v1"
MAX_STAGES = 8
MAX_EVENTS = 512


def normalize_campaign(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "campaign_id", "stages",
                        "required_score"}, "survival campaign source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported survival campaign schema")
    campaign_id = _id(obj["campaign_id"], "campaign id")
    stages = obj["stages"]
    if type(stages) is not list or not 1 <= len(stages) <= MAX_STAGES:
        raise SceneTravelError("invalid campaign stage count")
    result = []
    for entry in stages:
        stage = _object(entry, {"stage_id", "survival_source", "reward"},
                        "campaign stage")
        result.append({
            "stage_id": _id(stage["stage_id"], "campaign stage id"),
            "survival_source": normalize_survival(stage["survival_source"]),
            "reward": _limit(stage["reward"], "stage reward", 1, 1000),
        })
    ids = [s["stage_id"] for s in result]
    if len(set(ids)) != len(ids):
        raise SceneTravelError("duplicate campaign stage id")
    threshold = _limit(obj["required_score"], "campaign required score",
                       1, 8000)
    if threshold > sum(s["reward"] for s in result):
        raise SceneTravelError("campaign reward target is unattainable")
    return {
        "schema_version": SCHEMA, "campaign_id": campaign_id,
        "stages": result, "required_score": threshold,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          previous: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_digest": dig(source), "state_digest": dig(state),
        "tick": state["tick"],
        "parent_save_digest": dig(previous) if previous is not None else None,
    }


def new_campaign(source: Any) -> dict[str, Any]:
    spec = normalize_campaign(source)
    state = {
        "tick": 0, "stage_index": 0, "phase": "active",
        "score": 0, "completed": [],
        "stage": new_survival(spec["stages"][0]["survival_source"]),
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, spec = session["state"], session["source"]
    if old["phase"] != "active":
        raise SceneTravelError("campaign already terminal")
    if len(session["journal"]) >= MAX_EVENTS:
        raise SceneTravelError("campaign action budget exhausted")
    action = survival_action(raw)
    stage = survival_advance(old["stage"], action)
    index = old["stage_index"]
    state = {
        "tick": old["tick"] + 1, "stage_index": index,
        "phase": "active", "score": old["score"],
        "completed": list(old["completed"]), "stage": stage,
    }
    if stage["state"]["phase"] == "won":
        authored = spec["stages"][index]
        portable = export_survival(stage)
        state["score"] += authored["reward"]
        state["completed"].append({
            "stage_id": authored["stage_id"], "reward": authored["reward"],
            "state_digest": stage["state_digest"],
            "portable_checksum": portable["checksum"],
        })
        if index + 1 == len(spec["stages"]):
            state["phase"] = (
                "won" if state["score"] >= spec["required_score"] else "lost"
            )
        else:
            state["stage_index"] = index + 1
            state["stage"] = new_survival(
                spec["stages"][index + 1]["survival_source"]
            )
    elif stage["state"]["phase"] in ("lost", "draw"):
        state["phase"] = stage["state"]["phase"]
    event = {
        "sequence": old["tick"], "stage_index": index, "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": [*session["journal"], event],
        "save": _save(spec, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_campaign(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "campaign checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported campaign checkpoint")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_EVENTS:
        raise SceneTravelError("invalid campaign action journal")
    rebuilt = new_campaign(obj["source"])
    for entry in journal:
        if type(entry) is not dict or "action" not in entry:
            raise SceneTravelError("invalid campaign action entry")
        rebuilt = _advance(rebuilt, entry["action"])
        if rebuilt["journal"][-1] != entry:
            raise SceneTravelError("campaign action receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("campaign source, save or replay mismatch")
    return rebuilt


def resume_campaign(payload: Any, actions: Any) -> dict[str, Any]:
    current = verify_campaign(payload)
    if (type(actions) is not list
            or len(actions) + len(current["journal"]) > MAX_EVENTS):
        raise SceneTravelError("invalid campaign action batch")
    for action in actions:
        current = _advance(current, action)
    return current


def simulate_campaign(source: Any, actions: Any) -> dict[str, Any]:
    return resume_campaign(new_campaign(source), actions)


def export_campaign(payload: Any) -> dict[str, Any]:
    current = verify_campaign(payload)
    bundle = {
        "schema_version": BUNDLE,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
        "session": current,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_campaign(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    bundle = _object(payload, {
        "schema_version", "source_digest", "state_digest",
        "session", "checksum",
    }, "campaign export")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported campaign export")
    if bundle["checksum"] != dig({
        k: v for k, v in bundle.items() if k != "checksum"
    }):
        raise SceneTravelError("campaign export checksum mismatch")
    current = verify_campaign(bundle["session"])
    if (current["source_digest"] != bundle["source_digest"]
            or current["state_digest"] != bundle["state_digest"]):
        raise SceneTravelError("campaign export lineage mismatch")
    return current


def original_campaign() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    survival, actions = original_survival()
    second = {**survival, "max_health": 4, "turn_limit": 20}
    return {
        "schema_version": SCHEMA, "campaign_id": "original_survival_tour",
        "required_score": 30,
        "stages": [
            {"stage_id": "quay_crossing", "survival_source": survival,
             "reward": 10},
            {"stage_id": "gate_return", "survival_source": second,
             "reward": 20},
        ],
    }, [*actions, *actions]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-survival-campaign")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--source-json", required=True)
    simulate.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_campaign()
            result = simulate_campaign(source, actions)
        elif args.command == "simulate":
            result = simulate_campaign(
                _json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_campaign(
                _json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_campaign(_json(args.session_json))
        elif args.command == "export":
            result = export_campaign(_json(args.session_json))
        else:
            result = import_campaign(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
