"""Bounded, replay-proven stage-by-stage survival campaign route solver."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_survival_campaign import (
    _json, export_campaign, new_campaign, original_campaign,
    resume_campaign, verify_campaign,
)
from skeleton.game.gameplay.scene_tile_survival_route import (
    _limits, solve_survival,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_survival_campaign_route.v1"


def solve_campaign(source: Any = None, *, session: Any = None,
                   max_states: int = 1024,
                   max_depth: int = 32) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one campaign source or checkpoint")
    _limits(max_states, max_depth)
    current = new_campaign(source) if session is None else verify_campaign(session)
    start_digest = current["state_digest"]
    source_digest = current["source_digest"]
    actions: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []
    status = "found" if current["state"]["phase"] == "won" else "inconclusive"
    while current["state"]["phase"] == "active":
        index = current["state"]["stage_index"]
        stage = current["source"]["stages"][index]
        plan = solve_survival(
            session=current["state"]["stage"], max_states=max_states,
            max_depth=max_depth)
        stages.append({
            "stage_id": stage["stage_id"],
            "status": plan["status"], "route_digest": dig(plan),
            "actions": len(plan["actions"]),
        })
        if plan["status"] != "found":
            status = plan["status"]
            break
        if len(actions) + len(plan["actions"]) > 512:
            status = "inconclusive"
            break
        current = resume_campaign(current, plan["actions"])
        actions.extend(plan["actions"])
        if current["state"]["phase"] in ("lost", "draw"):
            status = current["state"]["phase"]
            break
    if current["state"]["phase"] == "won":
        status = "found"
    bundle = export_campaign(current) if status == "found" else None
    return {
        "schema_version": SCHEMA, "source_digest": source_digest,
        "initial_state_digest": start_digest, "status": status,
        "actions": actions, "stages": stages,
        "max_states": max_states, "max_depth": max_depth,
        "final_state_digest": (
            current["state_digest"] if status == "found" else None),
        "portable_checksum": bundle["checksum"] if bundle else None,
    }


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    if type(payload) is not dict or payload.get("schema_version") != SCHEMA:
        raise SceneTravelError("invalid campaign route proof")
    if payload.get("status") != "found":
        raise SceneTravelError("campaign route is not a winning witness")
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one campaign source or checkpoint")
    start = new_campaign(source) if session is None else verify_campaign(session)
    expected = solve_campaign(
        session=start, max_states=payload.get("max_states"),
        max_depth=payload.get("max_depth"))
    if payload != expected:
        raise SceneTravelError("campaign route proof mismatch")
    final = resume_campaign(start, payload["actions"])
    if (final["state"]["phase"] != "won"
            or final["state_digest"] != payload["final_state_digest"]
            or export_campaign(final)["checksum"] != payload["portable_checksum"]):
        raise SceneTravelError("campaign route replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-survival-campaign-route")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("solve", "verify"):
        p = sub.add_parser(command)
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--source-json")
        group.add_argument("--session-json")
        if command == "solve":
            p.add_argument("--max-states", type=int, default=1024)
            p.add_argument("--max-depth", type=int, default=32)
        else:
            p.add_argument("--plan-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_campaign()
            result = solve_campaign(source)
        else:
            options = (
                {"source": _json(args.source_json)}
                if args.source_json is not None
                else {"session": _json(args.session_json)}
            )
            if args.command == "solve":
                result = solve_campaign(
                    **options, max_states=args.max_states,
                    max_depth=args.max_depth)
            else:
                final = verify_plan(_json(args.plan_json), **options)
                result = {
                    "ok": True, "phase": final["state"]["phase"],
                    "state_digest": final["state_digest"],
                    "portable_checksum": export_campaign(final)["checksum"],
                }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
