"""Original eight-entrant offline combat league with canonical tournament replays.

Every match and awarded point is reconstructed from the existing turn-combat
tournament engine. League standings are not a trusted input or entitlement.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object,
)
from skeleton.game.gameplay.combat_tournament import (
    SCHEMA as TOURNAMENT_SCHEMA, finish_tournament, normalize_tournament,
    verify_tournament,
)

SCHEMA = "skeleton.combat_league.v1"
BUNDLE = "skeleton.combat_league_bundle.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROUNDS = 4
ENTRANTS = 8


def _bounded(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid league JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise CombatSessionError("league exceeds 2 MiB budget")
    return encoded


def _json(raw: str, label: str) -> Any:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise CombatSessionError(f"invalid or oversized {label} JSON")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    def nonfinite(_: str) -> None:
        raise ValueError("nonfinite JSON number")
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError(f"invalid {label} JSON") from exc


def normalize_league(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "world_id", "league_id", "entrants",
        "rounds", "match_turn_limit",
    }, "league")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported league schema")
    world_id = _id(obj["world_id"], "world_id")
    league_id = _id(obj["league_id"], "league_id")
    # Reserve suffix space for deterministic per-round tournament IDs.
    if len(league_id) > 48:
        raise CombatSessionError("league id too long for bracket identity")
    rounds = _integer(obj["rounds"], "rounds", 1, MAX_ROUNDS)
    turn_limit = _integer(obj["match_turn_limit"], "match_turn_limit", 1, 64)
    raw_entrants = obj["entrants"]
    if type(raw_entrants) is not list or len(raw_entrants) != ENTRANTS:
        raise CombatSessionError("league requires eight authored entrants")
    # Reuse the canonical tournament schema for actor stat validation.
    validated = []
    for index in (0, 4):
        tournament = normalize_tournament({
            "schema_version": TOURNAMENT_SCHEMA, "world_id": world_id,
            "tournament_id": f"{league_id}.source.{index}",
            "match_turn_limit": turn_limit,
            "entrants": raw_entrants[index:index + 4],
        })
        validated.extend(tournament["entrants"])
    if len({entrant["id"] for entrant in validated}) != ENTRANTS:
        raise CombatSessionError("duplicate league entrant")
    return {
        "schema_version": SCHEMA, "world_id": world_id, "league_id": league_id,
        "entrants": sorted(validated, key=lambda entry: entry["id"]),
        "rounds": rounds, "match_turn_limit": turn_limit,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=state["next_round"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_league(source: Any) -> dict[str, Any]:
    spec = normalize_league(source)
    state = {
        "next_round": 0, "phase": "active", "champion": None,
        "points": {entry["id"]: 0 for entry in spec["entrants"]},
        "rounds": [],
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "save": _save(spec, state),
    }


def _pairings(source: dict[str, Any], round_index: int) -> list[dict[str, Any]]:
    """Use distinct balanced partitions so entrants meet different opponents.

    A pure cyclic rotation of odd/even indices repeats the same two groups
    each round. Four independent partitions prevent that silent regression.
    """
    if type(round_index) is not int or not 0 <= round_index < source["rounds"]:
        raise CombatSessionError("league round outside authored schedule")
    ordered = source["entrants"]
    partitions = (
        (0, 2, 4, 6),
        (0, 1, 4, 5),
        (0, 1, 2, 3),
        (0, 3, 5, 6),
    )
    first = partitions[round_index]
    second = tuple(i for i in range(ENTRANTS) if i not in first)
    groups = ([ordered[i] for i in first], [ordered[i] for i in second])
    return [{
        "schema_version": TOURNAMENT_SCHEMA,
        "world_id": source["world_id"],
        "tournament_id": f'{source["league_id"]}.round{round_index + 1}.group{group + 1}',
        "entrants": list(entrants),
        "match_turn_limit": source["match_turn_limit"],
    } for group, entrants in enumerate(groups)]


def _points(tournament: dict[str, Any]) -> dict[str, int]:
    """Two points per semifinal win, three for final win, one for finalist."""
    result = {entry["id"]: 0 for entry in tournament["source"]["entrants"]}
    matches = tournament["state"]["matches"]
    for match in matches[:2]:
        if match["winner"] is not None:
            result[match["winner"]] += 2
    if len(matches) == 3 and matches[2]["winner"] is not None:
        final = matches[2]
        result[final["winner"]] += 3
        finalist = final["right"] if final["winner"] == final["left"] else final["left"]
        result[finalist] += 1
    return result


def _ranking(points: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"entrant_id": name, "points": points[name], "rank": index + 1}
        for index, name in enumerate(sorted(points, key=lambda n: (-points[n], n)))
    ]


def _advance_verified(session: dict[str, Any]) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise CombatSessionError("league already terminal")
    round_index = old["next_round"]
    if round_index >= source["rounds"]:
        raise CombatSessionError("league round budget exhausted")
    brackets = [verify_tournament(finish_tournament(group))
                for group in _pairings(source, round_index)]
    awarded = dict(old["points"])
    per_round = {name: 0 for name in awarded}
    for tournament in brackets:
        for name, points in _points(tournament).items():
            per_round[name] += points
            awarded[name] += points
    if any(value < 0 or value > 32 for value in awarded.values()):
        raise CombatSessionError("league points budget exceeded")
    rounds = [*old["rounds"], {
        "index": round_index, "brackets": brackets, "points_awarded": per_round,
    }]
    next_round = round_index + 1
    finished = next_round == source["rounds"]
    ranking = _ranking(awarded)
    champion = ranking[0]["entrant_id"] if finished and ranking[0]["points"] > 0 else None
    phase = ("won" if champion is not None else "draw") if finished else "active"
    state = {
        "next_round": next_round, "phase": phase, "champion": champion,
        "points": awarded, "rounds": rounds,
    }
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "save": _save(source, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_league(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "save",
    }, "league save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported league save schema")
    state = obj["state"]
    if type(state) is not dict or type(state.get("rounds")) is not list:
        raise CombatSessionError("invalid league round journal")
    if len(state["rounds"]) > MAX_ROUNDS:
        raise CombatSessionError("league replay round budget exceeded")
    rebuilt = new_league(obj["source"])
    for _ in state["rounds"]:
        rebuilt = _advance_verified(rebuilt)
    if rebuilt != obj:
        raise CombatSessionError("league replay or save lineage mismatch")
    return rebuilt


def advance_league(payload: Any) -> dict[str, Any]:
    return _advance_verified(verify_league(payload))


def finish_league(source: Any, *, resume: Any = None) -> dict[str, Any]:
    session = new_league(source) if resume is None else verify_league(resume)
    if session["source_digest"] != dig(normalize_league(source)):
        raise CombatSessionError("league resume source mismatch")
    while session["state"]["phase"] == "active":
        session = _advance_verified(session)
    return verify_league(session)


def standings(payload: Any) -> dict[str, Any]:
    session = verify_league(payload)
    state = session["state"]
    result = {
        "schema_version": SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "rounds_played": state["next_round"],
        "rounds_total": session["source"]["rounds"],
        "phase": state["phase"], "champion": state["champion"],
        "ranking": _ranking(state["points"]),
    }
    result["receipt"] = dig(result)
    return result


def export_league(payload: Any) -> dict[str, Any]:
    session = verify_league(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_league(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "league bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported league bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("league bundle checksum mismatch")
    session = verify_league(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise CombatSessionError("league bundle source mismatch")
    return session


def original_league() -> dict[str, Any]:
    """Eight original Harbor League characters with independent strengths."""
    return {
        "schema_version": SCHEMA, "world_id": "lantern_harbor",
        "league_id": "eight_lanterns", "rounds": 3, "match_turn_limit": 32,
        "entrants": [
            {"id": "amber_guard", "max_hp": 14, "attack": 5, "defense": 2, "speed": 3},
            {"id": "beacon_mender", "max_hp": 13, "attack": 4, "defense": 2, "speed": 5},
            {"id": "canal_runner", "max_hp": 11, "attack": 6, "defense": 1, "speed": 7},
            {"id": "dusk_cartographer", "max_hp": 15, "attack": 5, "defense": 3, "speed": 2},
            {"id": "ember_pilot", "max_hp": 12, "attack": 7, "defense": 1, "speed": 4},
            {"id": "fog_warden", "max_hp": 16, "attack": 4, "defense": 3, "speed": 1},
            {"id": "gale_scout", "max_hp": 12, "attack": 5, "defense": 2, "speed": 8},
            {"id": "harbor_healer", "max_hp": 17, "attack": 3, "defense": 4, "speed": 2},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-league")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    for command in ("verify", "advance", "resume", "standings", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = finish_league(original_league())
        elif args.command == "simulate":
            result = finish_league(_json(args.source_json, "league source"))
        elif args.command == "import":
            result = import_league(_json(args.bundle_json, "league bundle"))
        else:
            saved = _json(args.session_json, "league save")
            if args.command == "verify":
                result = verify_league(saved)
            elif args.command == "advance":
                result = advance_league(saved)
            elif args.command == "resume":
                verified = verify_league(saved)
                result = finish_league(verified["source"], resume=verified)
            elif args.command == "standings":
                result = standings(saved)
            else:
                result = export_league(saved)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
