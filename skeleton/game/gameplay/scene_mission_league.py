"""Offline, replay-verified scene mission competition.

A league is a local collection of canonical playable mission sessions, not a
remote leaderboard or an identity system. Scores are derived only from verified
gameplay and explicit bounded scoring rules. Checksums detect corruption, not
forged authorship; no external scores or arbitrary reward grants are accepted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import (
    MAX_BYTES as SESSION_BYTES, demo_actions,
    normalize_mission_world, original_mission, simulate_mission, verify_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_mission_league.v1"
BUNDLE = "skeleton.scene_mission_league_bundle.v1"
RULES = "skeleton.scene_mission_scoring.v1"
MAX_ENTRIES = 8
MAX_LEAGUE_BYTES = 8 * 1024 * 1024


def _bounded(value: Any, limit: int = MAX_LEAGUE_BYTES) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid league JSON") from exc
    if len(encoded) > limit:
        raise SceneTravelError("league byte budget exceeded")


def normalize_rules(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "rules_id", "action_cost", "mission_points",
        "reputation_multiplier", "victory_bonus", "defeat_penalty",
    }, "league scoring rules")
    if obj["schema_version"] != RULES:
        raise SceneTravelError("unsupported league scoring rules")
    return {
        "schema_version": RULES,
        "rules_id": _id(obj["rules_id"], "rules_id"),
        "action_cost": _limit(obj["action_cost"], "action_cost", 0, 100),
        "mission_points": _limit(obj["mission_points"], "mission_points", 0, 1000),
        "reputation_multiplier": _limit(
            obj["reputation_multiplier"], "reputation_multiplier", 0, 10,
        ),
        "victory_bonus": _limit(obj["victory_bonus"], "victory_bonus", 0, 5000),
        "defeat_penalty": _limit(obj["defeat_penalty"], "defeat_penalty", 0, 5000),
    }


def original_rules() -> dict[str, Any]:
    return {
        "schema_version": RULES, "rules_id": "harbor_challenge",
        "action_cost": 3, "mission_points": 50,
        "reputation_multiplier": 4, "victory_bonus": 200,
        "defeat_penalty": 100,
    }


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "league_digest": dig(payload)}


def new_league(source: Any, rules: Any) -> dict[str, Any]:
    spec = normalize_mission_world(source)
    scoring = normalize_rules(rules)
    return _seal({
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "rules": scoring, "rules_digest": dig(scoring),
        "revision": 0, "entries": [],
    })


def _score(session: dict[str, Any], rules: dict[str, Any]) -> int:
    state = session["state"]
    scene_phase = state["scene"]["state"]["phase"]
    return (
        len(state["missions"]) * rules["mission_points"]
        + state["reputation"] * rules["reputation_multiplier"]
        + (rules["victory_bonus"] if scene_phase == "won" else 0)
        - (rules["defeat_penalty"] if scene_phase == "lost" else 0)
        - state["tick"] * rules["action_cost"]
    )


def _append(league: dict[str, Any], attempt_id: str,
            session: Any) -> dict[str, Any]:
    attempt = _id(attempt_id, "attempt_id")
    if len(league["entries"]) >= MAX_ENTRIES:
        raise SceneTravelError("league entry budget exhausted")
    if any(e["attempt_id"] == attempt for e in league["entries"]):
        raise SceneTravelError("duplicate league attempt_id")
    verified = verify_mission(session)
    if verified["source_digest"] != league["source_digest"]:
        raise SceneTravelError("league attempt source mismatch")
    state = verified["state"]
    if state["phase"] != "finished":
        raise SceneTravelError("league attempt must finish a playable ending")
    if any(e["state_digest"] == verified["state_digest"]
           for e in league["entries"]):
        raise SceneTravelError("duplicate league replay")
    entry = {
        "attempt_id": attempt, "state_digest": verified["state_digest"],
        "ending": state["ending"], "turns": state["tick"],
        "missions": list(state["missions"]),
        "reputation": state["reputation"],
        "score": _score(verified, league["rules"]),
        "session": verified,
    }
    result = _seal({
        "schema_version": SCHEMA, "source": league["source"],
        "source_digest": league["source_digest"],
        "rules": league["rules"], "rules_digest": league["rules_digest"],
        "revision": league["revision"] + 1,
        "entries": [*league["entries"], entry],
    })
    _bounded(result)
    return result


def verify_league(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "rules",
        "rules_digest", "revision", "entries", "league_digest",
    }, "mission league")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported mission league schema")
    entries = obj["entries"]
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise SceneTravelError("invalid mission league entries")
    if type(obj["revision"]) is not int or obj["revision"] != len(entries):
        raise SceneTravelError("invalid league revision")
    rebuilt = new_league(obj["source"], obj["rules"])
    for entry in entries:
        record = _object(entry, {
            "attempt_id", "state_digest", "ending", "turns",
            "missions", "reputation", "score", "session",
        }, "league entry")
        rebuilt = _append(rebuilt, record["attempt_id"], record["session"])
        if rebuilt["entries"][-1] != record:
            raise SceneTravelError("league replay-derived score mismatch")
    if rebuilt != obj:
        raise SceneTravelError("league source, scoring or digest mismatch")
    return rebuilt


def submit_league(payload: Any, attempt_id: str, session: Any, *,
                  expected_digest: str) -> dict[str, Any]:
    league = verify_league(payload)
    if type(expected_digest) is not str or expected_digest != league["league_digest"]:
        raise SceneTravelError("stale league revision or expected digest")
    return _append(league, attempt_id, session)


def inspect_league(payload: Any) -> dict[str, Any]:
    league = verify_league(payload)
    entries = sorted(league["entries"], key=lambda e: (
        -e["score"], e["turns"], e["attempt_id"],
    ))
    return {
        "schema_version": SCHEMA, "source_digest": league["source_digest"],
        "rules_digest": league["rules_digest"],
        "league_digest": league["league_digest"],
        "revision": league["revision"],
        "ranking": [
            {"rank": index, "attempt_id": entry["attempt_id"],
             "ending": entry["ending"], "score": entry["score"],
             "turns": entry["turns"], "state_digest": entry["state_digest"]}
            for index, entry in enumerate(entries, 1)
        ],
    }


def export_league(payload: Any) -> dict[str, Any]:
    league = verify_league(payload)
    bundle = {
        "schema_version": BUNDLE, "league_digest": league["league_digest"],
        "source_digest": league["source_digest"],
        "league": league,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_league(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    bundle = _object(payload, {
        "schema_version", "league_digest", "source_digest", "league", "checksum",
    }, "league bundle")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported league bundle schema")
    if bundle["checksum"] != dig({
        k: v for k, v in bundle.items() if k != "checksum"
    }):
        raise SceneTravelError("league bundle checksum mismatch")
    league = verify_league(bundle["league"])
    if (league["league_digest"] != bundle["league_digest"]
            or league["source_digest"] != bundle["source_digest"]):
        raise SceneTravelError("league bundle source/digest mismatch")
    return league


def demo_league() -> dict[str, Any]:
    source = original_mission()
    league = new_league(source, original_rules())
    won = simulate_mission(source, demo_actions())
    league = submit_league(league, "restored", won,
                           expected_digest=league["league_digest"])
    actions = demo_actions()
    actions[0] = {**actions[0], "option_id": "decline"}
    actions[-1] = {**actions[-1], "ending_id": "unpledged_victory"}
    alternate = simulate_mission(source, actions)
    return submit_league(league, "unpledged", alternate,
                         expected_digest=league["league_digest"])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-league")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name in ("inspect", "verify", "export"):
        sub.add_parser(name).add_argument("--league-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    new = sub.add_parser("new")
    new.add_argument("--source-json", required=True)
    new.add_argument("--rules-json", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--league-json", required=True)
    submit.add_argument("--attempt-id", required=True)
    submit.add_argument("--session-json", required=True)
    submit.add_argument("--expected-digest", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_league()
        elif args.command == "new":
            result = new_league(
                _strict_json(args.source_json, "league source", max_bytes=SESSION_BYTES),
                _strict_json(args.rules_json, "league rules", max_bytes=8192),
            )
        elif args.command == "import":
            result = import_league(_strict_json(
                args.bundle_json, "league bundle", max_bytes=MAX_LEAGUE_BYTES,
            ))
        else:
            league = _strict_json(
                args.league_json, "league", max_bytes=MAX_LEAGUE_BYTES,
            )
            if args.command == "inspect":
                result = inspect_league(league)
            elif args.command == "verify":
                result = verify_league(league)
            elif args.command == "export":
                result = export_league(league)
            else:
                result = submit_league(
                    league, args.attempt_id,
                    _strict_json(args.session_json, "mission attempt",
                                 max_bytes=SESSION_BYTES),
                    expected_digest=args.expected_digest,
                )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
