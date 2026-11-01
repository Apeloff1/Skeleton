"""Playable league coaching career with deterministic choices and sealed seasons.

The player chooses one entrant to train before each season, or rests. Every
result is rebuilt from the canonical league simulator; points and rewards are
never trusted from a client-supplied save. The journal is the replay source.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _integer, _object
from skeleton.game.gameplay.combat_league import (
    SCHEMA as LEAGUE_SCHEMA, _bounded, _json, finish_league, normalize_league,
    original_league, standings, verify_league,
)

SCHEMA = "skeleton.combat_league_career.v1"
BUNDLE = "skeleton.combat_league_career_bundle.v1"
MAX_SEASONS = 4
STATS = {"max_hp": 10000, "attack": 1000, "defense": 1000, "speed": 1000}


def original_career() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "career_id": "harbor_coaching_trial",
        "league": original_league(), "seasons": 3, "training_tokens": 2,
    }


def normalize_career(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "career_id", "league",
                        "seasons", "training_tokens"}, "career source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported career source schema")
    career_id = _id(obj["career_id"], "career_id")
    if len(career_id) > 48:
        raise CombatSessionError("career id too long")
    league = normalize_league(obj["league"])
    # Leave space for the deterministic .sN season suffix within the
    # canonical league ID bound, so source validity implies playability.
    if len(league["league_id"]) > 45:
        raise CombatSessionError("career league id too long for season identity")
    if league["schema_version"] != LEAGUE_SCHEMA:
        raise CombatSessionError("unsupported career league")
    seasons = _integer(obj["seasons"], "seasons", 1, MAX_SEASONS)
    tokens = _integer(obj["training_tokens"], "training_tokens", 0, seasons)
    spec = {
        "schema_version": SCHEMA, "career_id": career_id, "league": league,
        "seasons": seasons, "training_tokens": tokens,
    }
    _bounded(spec)
    return spec


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["league"]["world_id"], schema_version=1,
        tick=state["next_season"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_career(source: Any) -> dict[str, Any]:
    spec = normalize_career(source)
    state = {
        "next_season": 0, "phase": "active", "tokens_remaining": spec["training_tokens"],
        "season_journal": [], "wins": {e["id"]: 0 for e in spec["league"]["entrants"]},
        "champion": None,
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "save": _save(spec, state),
    }


def _choice(raw: Any, source: dict[str, Any], tokens: int) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid career choice")
    kind = raw.get("kind")
    if kind == "rest":
        _object(raw, {"kind"}, "rest choice")
        return {"kind": "rest"}
    if kind != "train":
        raise CombatSessionError("unknown career choice")
    obj = _object(raw, {"kind", "entrant_id", "stat"}, "training choice")
    if tokens <= 0:
        raise CombatSessionError("no training tokens remain")
    entrant_id = _id(obj["entrant_id"], "entrant_id")
    if entrant_id not in {e["id"] for e in source["league"]["entrants"]}:
        raise CombatSessionError("unknown career entrant")
    stat = obj["stat"]
    if type(stat) is not str or stat not in STATS:
        raise CombatSessionError("invalid training stat")
    return {"kind": "train", "entrant_id": entrant_id, "stat": stat}


def _league_for_season(source: dict[str, Any], season: int,
                       choice: dict[str, Any]) -> dict[str, Any]:
    league = json.loads(_bounded(source["league"]).decode("utf-8"))
    # A season ID is distinct from the underlying authored league identity.
    suffix = f".s{season + 1}"
    if len(league["league_id"]) + len(suffix) > 64:
        raise CombatSessionError("career league id overflow")
    league["league_id"] += suffix
    if choice["kind"] == "train":
        entrant = next(e for e in league["entrants"] if e["id"] == choice["entrant_id"])
        stat = choice["stat"]
        if entrant[stat] >= STATS[stat]:
            raise CombatSessionError("training would exceed actor stat bound")
        entrant[stat] += 1
    return normalize_league(league)


def _advance_verified(session: dict[str, Any], raw_choice: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active" or old["next_season"] >= source["seasons"]:
        raise CombatSessionError("career already terminal")
    choice = _choice(raw_choice, source, old["tokens_remaining"])
    league_source = _league_for_season(source, old["next_season"], choice)
    result = verify_league(finish_league(league_source))
    board = standings(result)
    winner = board["champion"]
    wins = dict(old["wins"])
    if winner is not None:
        wins[winner] += 1
    entry = {
        "index": old["next_season"], "choice": choice,
        "league_source_digest": dig(league_source), "league": result,
        "winner": winner,
    }
    entry["receipt"] = dig(entry)
    journal = [*old["season_journal"], entry]
    next_season = old["next_season"] + 1
    done = next_season == source["seasons"]
    ranking = sorted(wins, key=lambda entrant: (-wins[entrant], entrant))
    champion = ranking[0] if done and wins[ranking[0]] > 0 else None
    state = {
        "next_season": next_season, "phase": ("won" if champion else "draw") if done else "active",
        "tokens_remaining": old["tokens_remaining"] - (choice["kind"] == "train"),
        "season_journal": journal, "wins": wins, "champion": champion,
    }
    saved = {
        "schema_version": SCHEMA, "source": source, "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state), "save": _save(source, state, session["save"]),
    }
    _bounded(saved)
    return saved


def verify_career(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "state", "state_digest", "save"}, "career save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported career save schema")
    state = obj["state"]
    if type(state) is not dict or type(state.get("season_journal")) is not list:
        raise CombatSessionError("invalid career journal")
    journal = state["season_journal"]
    if len(journal) > MAX_SEASONS:
        raise CombatSessionError("career replay budget exceeded")
    rebuilt = new_career(obj["source"])
    for entry in journal:
        if type(entry) is not dict or "choice" not in entry:
            raise CombatSessionError("invalid career journal event")
        rebuilt = _advance_verified(rebuilt, entry["choice"])
        if rebuilt["state"]["season_journal"][-1] != entry:
            raise CombatSessionError("career season replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("career save or lineage mismatch")
    return rebuilt


def advance_career(raw: Any, choice: Any) -> dict[str, Any]:
    return _advance_verified(verify_career(raw), choice)


def finish_career(source: Any, choices: Sequence[Any],
                  *, resume: Any = None) -> dict[str, Any]:
    if type(choices) not in (list, tuple) or len(choices) > MAX_SEASONS:
        raise CombatSessionError("invalid career choice list")
    current = new_career(source) if resume is None else verify_career(resume)
    if current["source_digest"] != dig(normalize_career(source)):
        raise CombatSessionError("career resume source mismatch")
    for choice in choices:
        current = advance_career(current, choice)
    return current


def career_board(raw: Any) -> dict[str, Any]:
    saved = verify_career(raw)
    state = saved["state"]
    board = {
        "schema_version": SCHEMA, "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "phase": state["phase"],
        "seasons_played": state["next_season"],
        "seasons_total": saved["source"]["seasons"],
        "tokens_remaining": state["tokens_remaining"], "champion": state["champion"],
        "ranking": [{"entrant_id": name, "wins": state["wins"][name]}
                    for name in sorted(state["wins"], key=lambda n: (-state["wins"][n], n))],
    }
    board["receipt"] = dig(board)
    return board


def export_career(raw: Any) -> dict[str, Any]:
    saved = verify_career(raw)
    bundle = {
        "schema_version": BUNDLE, "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"], "session": saved,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_career(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source_digest", "state_digest",
                        "session", "checksum"}, "career bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported career bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("career bundle checksum mismatch")
    saved = verify_career(obj["session"])
    if obj["source_digest"] != saved["source_digest"] or obj["state_digest"] != saved["state_digest"]:
        raise CombatSessionError("career bundle source mismatch")
    return saved


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-career")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    new = sub.add_parser("new")
    new.add_argument("--source-json", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--session-json", required=True)
    advance.add_argument("--choice-json", required=True)
    for name in ("verify", "board", "export"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = finish_career(original_career(), [{"kind": "rest"}] * 3)
        elif args.command == "new":
            result = new_career(_json(args.source_json, "career source"))
        elif args.command == "import":
            result = import_career(_json(args.bundle_json, "career bundle"))
        else:
            session = _json(args.session_json, "career save")
            if args.command == "advance":
                result = advance_career(session, _json(args.choice_json, "career choice"))
            elif args.command == "verify":
                result = verify_career(session)
            elif args.command == "board":
                result = career_board(session)
            else:
                result = export_career(session)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
