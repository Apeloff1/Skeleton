"""Deterministic one-season coaching advisor with replayed candidate outcomes.

The advisor evaluates actual league matches; it never promises an optimal
multi-season strategy or invents rewards. Its recommendation is advisory.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _object
from skeleton.game.gameplay.combat_league import _bounded, _json, standings
from skeleton.game.gameplay.combat_league_career import (
    advance_career, new_career, original_career, verify_career,
)

SCHEMA = "skeleton.combat_league_career_advice.v1"
STATS = ("attack", "defense", "max_hp", "speed")
MAX_CANDIDATES = 5


def _candidates(saved: dict[str, Any], target: str) -> list[dict[str, str]]:
    choices = [{"kind": "rest"}]
    if saved["state"]["tokens_remaining"] > 0:
        choices.extend({"kind": "train", "entrant_id": target, "stat": stat}
                       for stat in STATS)
    return choices


def advise_career(raw: Any, target_id: Any) -> dict[str, Any]:
    saved = verify_career(raw)
    target = _id(target_id, "target_id")
    if target not in saved["state"]["wins"]:
        raise CombatSessionError("target entrant not authored")
    if saved["state"]["phase"] != "active":
        raise CombatSessionError("career already terminal")
    evaluated = []
    for choice in _candidates(saved, target):
        try:
            next_saved = advance_career(saved, choice)
        except CombatSessionError:
            # A capped stat is not a legal candidate. Other failures are
            # fail-closed in the source engine and are not recommendations.
            if choice["kind"] == "train":
                entrant = next(e for e in saved["source"]["league"]["entrants"]
                               if e["id"] == target)
                cap = 10000 if choice["stat"] == "max_hp" else 1000
                if entrant[choice["stat"]] >= cap:
                    continue
            raise
        season = next_saved["state"]["season_journal"][-1]
        board = standings(season["league"])
        points = next(row["points"] for row in board["ranking"]
                      if row["entrant_id"] == target)
        score = [
            int(season["winner"] == target), points,
            int(choice["kind"] == "rest"),
        ]
        evaluated.append({
            "choice": choice, "score": score,
            "winner": season["winner"],
            "state_digest": next_saved["state_digest"],
            "league_receipt": season["receipt"],
        })
    if not evaluated or len(evaluated) > MAX_CANDIDATES:
        raise CombatSessionError("career advice candidate budget invalid")
    best = max(evaluated, key=lambda candidate: tuple(candidate["score"]))
    predicted = advance_career(saved, best["choice"])
    result = {
        "schema_version": SCHEMA, "source_digest": saved["source_digest"],
        "starting_state_digest": saved["state_digest"],
        "target_id": target, "season": saved["state"]["next_season"],
        "evaluated": evaluated, "recommended_choice": best["choice"],
        "predicted_session": predicted, "predicted_state_digest": predicted["state_digest"],
        "claim": "one_season_replay_only",
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def verify_advice(raw: Any, result: Any) -> dict[str, Any]:
    _bounded(result)
    obj = _object(result, {
        "schema_version", "source_digest", "starting_state_digest",
        "target_id", "season", "evaluated", "recommended_choice",
        "predicted_session", "predicted_state_digest", "claim", "receipt",
    }, "career advice")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "one_season_replay_only":
        raise CombatSessionError("unsupported career advice claim")
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("career advice receipt mismatch")
    expected = advise_career(raw, obj["target_id"])
    if obj != expected:
        raise CombatSessionError("career advice replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-career-advice")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    advise = sub.add_parser("advise")
    advise.add_argument("--session-json", required=True)
    advise.add_argument("--target-id", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--advice-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = advise_career(new_career(original_career()), "amber_guard")
        elif args.command == "advise":
            result = advise_career(_json(args.session_json, "career save"), args.target_id)
        else:
            result = verify_advice(_json(args.session_json, "career save"),
                                   _json(args.advice_json, "career advice"))
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
