"""Deterministic four-entrant tournament built on the canonical turn-combat engine.

All three duels use the existing replay-verified turn engine and tactical
policy. A tournament save is reconstructed from authored source, never trusted
as a record of wins or rewards. Digests detect corruption, not authorship.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.tactical_policy import run_autoplay
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, SCHEMA as COMBAT_SCHEMA,
    _id, _integer, _object, _parse_json, verify_session,
)

SCHEMA = "skeleton.combat_tournament.v1"
BUNDLE_SCHEMA = "skeleton.combat_tournament_bundle.v1"
MAX_MATCH_TURNS = 64
MAX_BUNDLE_BYTES = MAX_CLI_BYTES


def normalize_tournament(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "world_id", "tournament_id",
                        "entrants", "match_turn_limit"}, "tournament")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported tournament schema")
    world_id = _id(obj["world_id"], "world_id")
    tournament_id = _id(obj["tournament_id"], "tournament_id")
    turn_limit = _integer(obj["match_turn_limit"], "match_turn_limit", 1, MAX_MATCH_TURNS)
    entrants = obj["entrants"]
    if type(entrants) is not list or len(entrants) != 4:
        raise CombatSessionError("tournament requires exactly four entrants")
    result = []
    seen = set()
    for raw_entrant in entrants:
        entry = _object(raw_entrant, {"id", "max_hp", "attack", "defense", "speed"},
                        "tournament entrant")
        name = _id(entry["id"], "entrant id")
        if name in seen:
            raise CombatSessionError("duplicate tournament entrant")
        seen.add(name)
        result.append({
            "id": name,
            "max_hp": _integer(entry["max_hp"], "max_hp", 1, 10000),
            "attack": _integer(entry["attack"], "attack", 1, 1000),
            "defense": _integer(entry["defense"], "defense", 0, 1000),
            "speed": _integer(entry["speed"], "speed", 0, 1000),
        })
    return {"schema_version": SCHEMA, "world_id": world_id,
            "tournament_id": tournament_id, "entrants": result,
            "match_turn_limit": turn_limit}


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=sum(item["combat"]["state"]["tick"] for item in state["matches"]),
        state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_tournament(source: Any) -> dict[str, Any]:
    spec = normalize_tournament(source)
    state = {"next_match": 0, "phase": "active", "champion": None, "matches": []}
    return {"schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
            "state": state, "state_digest": dig(state), "save": _save(spec, state)}


def _pair(snapshot: dict[str, Any]) -> tuple[str, str]:
    state, entrants = snapshot["state"], snapshot["source"]["entrants"]
    index = state["next_match"]
    if index == 0:
        return entrants[0]["id"], entrants[1]["id"]
    if index == 1:
        return entrants[2]["id"], entrants[3]["id"]
    if index == 2:
        matches = state["matches"]
        if len(matches) != 2 or any(item["winner"] is None for item in matches):
            raise CombatSessionError("final requires two decisive semifinals")
        return matches[0]["winner"], matches[1]["winner"]
    raise CombatSessionError("tournament bracket already complete")


def _advance_verified(snapshot: dict[str, Any]) -> dict[str, Any]:
    spec, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise CombatSessionError("tournament already terminal")
    left, right = _pair(snapshot)
    actors = {entry["id"]: entry for entry in spec["entrants"]}
    scenario = {
        "schema_version": COMBAT_SCHEMA, "world_id": spec["world_id"],
        "encounter_id": f'{spec["tournament_id"]}.round{old["next_match"] + 1}',
        "turn_limit": spec["match_turn_limit"],
        "actors": [{**actors[name], "team": name} for name in (left, right)],
    }
    combat = run_autoplay(scenario)
    combat = verify_session(combat)
    winner = combat["state"]["winner"] if combat["state"]["phase"] == "won" else None
    match = {"index": old["next_match"], "left": left, "right": right,
             "winner": winner, "combat": combat}
    matches = [*old["matches"], match]
    next_match = old["next_match"] + 1
    phase = "draw" if winner is None else ("won" if next_match == 3 else "active")
    state = {"next_match": next_match, "phase": phase,
             "champion": winner if phase == "won" else None, "matches": matches}
    return {"schema_version": SCHEMA, "source": spec,
            "source_digest": snapshot["source_digest"], "state": state,
            "state_digest": dig(state), "save": _save(spec, state, snapshot["save"])}


def verify_tournament(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "source", "source_digest",
                            "state", "state_digest", "save"}, "tournament save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported tournament save")
    rebuilt = new_tournament(obj["source"])
    state = obj["state"]
    if type(state) is not dict or type(state.get("matches")) is not list:
        raise CombatSessionError("invalid tournament match journal")
    if len(state["matches"]) > 3:
        raise CombatSessionError("tournament match budget exceeded")
    for _ in state["matches"]:
        rebuilt = _advance_verified(rebuilt)
    if rebuilt != obj:
        raise CombatSessionError("tournament replay or save lineage mismatch")
    return rebuilt


def advance_tournament(snapshot: Any) -> dict[str, Any]:
    return _advance_verified(verify_tournament(snapshot))


def finish_tournament(source: Any, *, resume: Any = None) -> dict[str, Any]:
    session = new_tournament(source) if resume is None else verify_tournament(resume)
    if session["source_digest"] != dig(normalize_tournament(source)):
        raise CombatSessionError("tournament resume source mismatch")
    while session["state"]["phase"] == "active":
        session = _advance_verified(session)
    return verify_tournament(session)


def _encoded(payload: Any) -> bytes:
    try:
        result = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise CombatSessionError("invalid tournament JSON") from exc
    if len(result) > MAX_BUNDLE_BYTES:
        raise CombatSessionError("tournament portable payload exceeds 128 KiB")
    return result


def export_tournament(snapshot: Any) -> dict[str, Any]:
    session = verify_tournament(snapshot)
    record = {"schema_version": BUNDLE_SCHEMA, "kind": "offline_tournament",
              "source_digest": session["source_digest"],
              "state_digest": session["state_digest"], "session": session}
    bundle = {**record, "checksum": dig(record)}
    _encoded(bundle)
    return bundle


def import_tournament(payload: Any) -> dict[str, Any]:
    _encoded(payload)
    obj = _object(payload, {"schema_version", "kind", "source_digest",
                            "state_digest", "session", "checksum"},
                  "tournament bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA or obj["kind"] != "offline_tournament":
        raise CombatSessionError("unsupported tournament bundle")
    if type(obj["checksum"]) is not str or len(obj["checksum"]) != 64:
        raise CombatSessionError("invalid tournament checksum")
    if dig({key: value for key, value in obj.items() if key != "checksum"}) != obj["checksum"]:
        raise CombatSessionError("tournament checksum mismatch")
    session = verify_tournament(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("tournament bundle identity mismatch")
    return session


def original_tournament() -> dict[str, Any]:
    """Original Lantern Harbor bracket with distinct player strengths."""
    return {
        "schema_version": SCHEMA, "world_id": "lantern_harbor",
        "tournament_id": "four_tides", "match_turn_limit": 32,
        "entrants": [
            {"id": "lantern_scout", "max_hp": 14, "attack": 6, "defense": 2, "speed": 5},
            {"id": "marsh_warden", "max_hp": 12, "attack": 4, "defense": 2, "speed": 3},
            {"id": "harbor_guard", "max_hp": 13, "attack": 5, "defense": 2, "speed": 4},
            {"id": "tide_runner", "max_hp": 11, "attack": 4, "defense": 1, "speed": 6},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-tournament")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Play original three-match offline bracket")
    sim = commands.add_parser("simulate", help="Run authored bracket")
    sim.add_argument("--source-json", required=True)
    for name in ("verify", "advance", "resume", "export"):
        command = commands.add_parser(name)
        command.add_argument("--session-json", required=True)
    imp = commands.add_parser("import", help="Verify portable replay bundle")
    imp.add_argument("--bundle-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = finish_tournament(original_tournament())
        elif args.command == "simulate":
            result = finish_tournament(_parse_json(args.source_json, "tournament"))
        elif args.command == "import":
            result = import_tournament(_parse_json(args.bundle_json, "bundle"))
        else:
            session = _parse_json(args.session_json, "session")
            if args.command == "verify":
                result = verify_tournament(session)
            elif args.command == "advance":
                result = advance_tournament(session)
            elif args.command == "resume":
                verified = verify_tournament(session)
                result = finish_tournament(verified["source"], resume=verified)
            else:
                result = export_tournament(session)
        print(_encoded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
