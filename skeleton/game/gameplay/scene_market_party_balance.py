"""Replay-derived cooperative role balance audit for playable market games.

This is a production inspection surface, not a gameplay reducer or actor
authentication service. It never changes credits, inventory, or outcomes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    ROLES, export_party, import_party, original_party,
    simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_balance.v1"
MAX_BYTES = 2 * 1024 * 1024


def analyze_party_balance(checkpoint: Any) -> dict[str, Any]:
    session = verify_party(checkpoint)
    players = session["source"]["players"]
    contributions = session["state"]["contributions"]
    passes = session["state"]["passes"]
    by_player = []
    role_totals = {role: 0 for role in ROLES}
    actions = []
    for player in players:
        name = player["player_id"]
        counts = contributions[name]
        for role in ROLES:
            role_totals[role] += counts[role]
        active = sum(counts.values())
        total = active + passes[name]
        actions.append(active)
        by_player.append({"player_id": name, "roles": player["roles"],
                          "role_actions": dict(counts),
                          "productive_turns": active,
                          "passes": passes[name], "total_turns": total})
    if sum(p["total_turns"] for p in by_player) != len(session["journal"]):
        raise SceneTravelError("cooperative balance turn accounting diverged")
    observed = {role: 0 for role in ROLES}
    for event in session["journal"]:
        kind = event["turn"]["action"]["kind"]
        for role, action in ROLES.items():
            if action == kind:
                observed[role] += 1
    if observed != role_totals:
        raise SceneTravelError("cooperative balance role accounting diverged")
    phase = session["state"]["market"]["state"]["phase"]
    result = {"schema_version": SCHEMA,
              "source_digest": session["source_digest"],
              "state_digest": session["state_digest"],
              "save_digest": dig(session["save"]),
              "phase": phase, "turns": len(session["journal"]),
              "players": by_player,
              "role_totals": role_totals,
              "unused_roles": sorted(role for role, count in role_totals.items()
                                     if count == 0),
              "productive_turn_gap": max(actions) - min(actions),
              "qualification": "replay_observation_not_player_authentication"}
    result["checksum"] = dig(result)
    _bounded(result, MAX_BYTES)
    return result


def verify_party_balance(checkpoint: Any, report: Any) -> dict[str, Any]:
    _bounded(report, MAX_BYTES)
    expected = analyze_party_balance(checkpoint)
    if type(report) is not dict or report != expected:
        raise SceneTravelError("cooperative balance report altered")
    return expected


def accept_balance() -> dict[str, Any]:
    source, turns = original_party()
    session = simulate_party(source, turns)
    restored = import_party(json.loads(json.dumps(export_party(session))))
    if restored != session:
        raise SceneTravelError("cooperative balance portable save diverged")
    report = analyze_party_balance(restored)
    if verify_party_balance(restored, report) != report:
        raise SceneTravelError("cooperative balance receipt diverged")
    if report["phase"] != "won":
        raise SceneTravelError("cooperative balance acceptance did not win")
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-balance")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--session-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_balance()
        elif args.command == "inspect":
            result = analyze_party_balance(_json(args.session_json))
        else:
            result = verify_party_balance(_json(args.session_json),
                                          _json(args.report_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
