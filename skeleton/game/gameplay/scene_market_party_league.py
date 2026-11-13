"""Replay-scored cooperative market league with no synthetic rewards.

Every ranked attempt must be a canonical, completed party replay for the
league's exact source. A score is derived from earned credits, inventory,
contributions and actual turns; it never mutates the market or party.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    normalize_party, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_party_league.v1"
BUNDLE = "skeleton.scene_market_party_league_bundle.v1"
MAX_ATTEMPTS = 16
MAX_BYTES = 2 * 1024 * 1024
DEFAULT_RULES = {"victory": 1000, "credits": 3, "goods": 5,
                 "contributions": 7, "turns": -2, "passes": -3}


def _limit(payload: Any) -> None:
    _bounded(payload, MAX_BYTES)


def normalize_rules(raw: Any) -> dict[str, int]:
    _limit(raw)
    obj = _object(raw, set(DEFAULT_RULES), "cooperative league scoring rules")
    result = {}
    for name, value in obj.items():
        if type(value) is not int or not -1000 <= value <= 1000:
            raise SceneTravelError("invalid cooperative league scoring weight")
        if (name in ("victory", "credits", "goods", "contributions")
                and value < 0) or (name in ("turns", "passes") and value > 0):
            raise SceneTravelError("cooperative league scoring rewards failure")
        result[name] = value
    if result["victory"] <= 0:
        raise SceneTravelError("cooperative league victory must be rewarded")
    return {name: result[name] for name in DEFAULT_RULES}


def _state_digest(revision: int, entries: list[dict[str, Any]]) -> str:
    return dig({"revision": revision, "entries": entries})


def new_league(source: Any, rules: Any = None) -> dict[str, Any]:
    spec = normalize_party(source)
    scoring = normalize_rules(DEFAULT_RULES if rules is None else rules)
    result = {"schema_version": SCHEMA, "source": spec,
              "source_digest": dig(spec), "rules": scoring,
              "revision": 0, "entries": [], "journal": [],
              "state_digest": _state_digest(0, [])}
    _limit(result)
    return result


def score_party(checkpoint: Any, rules: Any = None) -> dict[str, Any]:
    session = verify_party(checkpoint)
    scoring = normalize_rules(DEFAULT_RULES if rules is None else rules)
    market = session["state"]["market"]["state"]
    if market["phase"] != "won":
        raise SceneTravelError("cooperative league requires earned victory")
    credits = market["credits"]
    goods = sum(market["goods"].values())
    contributions = sum(sum(values.values())
                        for values in session["state"]["contributions"].values())
    passes = sum(session["state"]["passes"].values())
    turns = session["state"]["sequence"]
    if any(type(x) is not int or x < 0 for x in
           (credits, goods, contributions, passes, turns)):
        raise SceneTravelError("invalid cooperative league earned metrics")
    metrics = {"victory": 1, "credits": credits, "goods": goods,
               "contributions": contributions, "turns": turns,
               "passes": passes}
    score = sum(metrics[name] * scoring[name] for name in DEFAULT_RULES)
    return {"score": score, "metrics": metrics,
            "party_state_digest": session["state_digest"],
            "source_digest": session["source_digest"],
            "save_digest": dig(session["save"])}


def _record(league: dict[str, Any], attempt_id: Any,
            checkpoint: Any, expected_revision: Any) -> dict[str, Any]:
    if type(expected_revision) is not int or expected_revision != league["revision"]:
        raise SceneTravelError("stale cooperative league revision")
    if league["revision"] >= MAX_ATTEMPTS:
        raise SceneTravelError("cooperative league attempt budget exhausted")
    name = _id(attempt_id, "cooperative league attempt id")
    if len(name) > 48 or any(e["attempt_id"] == name for e in league["entries"]):
        raise SceneTravelError("duplicate or invalid cooperative league attempt")
    session = verify_party(checkpoint)
    if session["source_digest"] != league["source_digest"]:
        raise SceneTravelError("cooperative league source mismatch")
    receipt = score_party(session, league["rules"])
    entry = {"attempt_id": name, **receipt}
    entries = [*league["entries"], entry]
    revision = league["revision"] + 1
    state_digest = _state_digest(revision, entries)
    action = {"attempt_id": name, "checkpoint": copy.deepcopy(session),
              "expected_revision": expected_revision}
    event = {"sequence": league["revision"], "action": action,
             "before_state_digest": league["state_digest"],
             "after_state_digest": state_digest, "entry_digest": dig(entry)}
    event["receipt"] = dig(event)
    result = {"schema_version": SCHEMA, "source": league["source"],
              "source_digest": league["source_digest"],
              "rules": league["rules"], "revision": revision,
              "entries": entries, "journal": [*league["journal"], event],
              "state_digest": state_digest}
    _limit(result)
    return result


def verify_league(raw: Any) -> dict[str, Any]:
    _limit(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "rules", "revision", "entries", "journal",
                        "state_digest"}, "cooperative league")
    if (obj["schema_version"] != SCHEMA or type(obj["journal"]) is not list
            or len(obj["journal"]) > MAX_ATTEMPTS):
        raise SceneTravelError("invalid cooperative league schema or journal")
    rebuilt = new_league(obj["source"], obj["rules"])
    for event in obj["journal"]:
        if type(event) is not dict or type(event.get("action")) is not dict:
            raise SceneTravelError("invalid cooperative league event")
        action = _object(event["action"],
                         {"attempt_id", "checkpoint", "expected_revision"},
                         "cooperative league event action")
        rebuilt = _record(rebuilt, action["attempt_id"],
                          action["checkpoint"], action["expected_revision"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("cooperative league event receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("cooperative league replay mismatch")
    return rebuilt


def record_attempt(league: Any, attempt_id: str, checkpoint: Any,
                   *, expected_revision: int) -> dict[str, Any]:
    return _record(verify_league(league), attempt_id, checkpoint, expected_revision)


def rank_league(league: Any) -> dict[str, Any]:
    verified = verify_league(league)
    ranking = sorted(verified["entries"],
                     key=lambda e: (-e["score"], e["metrics"]["turns"],
                                    e["attempt_id"]))
    result = {"schema_version": "skeleton.scene_market_party_ranking.v1",
              "source_digest": verified["source_digest"],
              "league_state_digest": verified["state_digest"],
              "revision": verified["revision"],
              "ranking": [{"rank": i + 1, **copy.deepcopy(e)}
                          for i, e in enumerate(ranking)],
              "qualification": "offline_replay_score_not_actor_authentication"}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def export_league(league: Any) -> dict[str, Any]:
    verified = verify_league(league)
    result = {"schema_version": BUNDLE, "league": verified,
              "source_digest": verified["source_digest"],
              "state_digest": verified["state_digest"]}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def import_league(raw: Any) -> dict[str, Any]:
    _limit(raw)
    obj = _object(raw, {"schema_version", "league", "source_digest",
                        "state_digest", "checksum"}, "cooperative league bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported cooperative league bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items()
                               if k != "checksum"}):
        raise SceneTravelError("cooperative league export checksum mismatch")
    verified = verify_league(obj["league"])
    if (verified["source_digest"] != obj["source_digest"]
            or verified["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("cooperative league bundle lineage mismatch")
    return verified


def accept_league() -> dict[str, Any]:
    source, turns = original_party()
    played = simulate_party(source, turns)
    league = record_attempt(new_league(source), "original-win", played,
                            expected_revision=0)
    restored = import_league(json.loads(json.dumps(export_league(league))))
    ranking = rank_league(restored)
    if (ranking["revision"] != 1 or len(ranking["ranking"]) != 1
            or ranking["ranking"][0]["party_state_digest"] != played["state_digest"]):
        raise SceneTravelError("cooperative league export acceptance diverged")
    return ranking


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-league")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    create = sub.add_parser("create")
    create.add_argument("--source-json", required=True)
    create.add_argument("--rules-json")
    record = sub.add_parser("record")
    record.add_argument("--league-json", required=True)
    record.add_argument("--attempt-id", required=True)
    record.add_argument("--checkpoint-json", required=True)
    record.add_argument("--expected-revision", type=int, required=True)
    for command in ("rank", "verify", "export"):
        sub.add_parser(command).add_argument("--league-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command in ("demo", "accept"):
            result = accept_league()
        elif args.command == "create":
            result = new_league(_json(args.source_json),
                                _json(args.rules_json) if args.rules_json else None)
        elif args.command == "record":
            result = record_attempt(_json(args.league_json), args.attempt_id,
                                    _json(args.checkpoint_json),
                                    expected_revision=args.expected_revision)
        elif args.command == "rank":
            result = rank_league(_json(args.league_json))
        elif args.command == "verify":
            result = verify_league(_json(args.league_json))
        elif args.command == "export":
            result = export_league(_json(args.league_json))
        else:
            result = import_league(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
