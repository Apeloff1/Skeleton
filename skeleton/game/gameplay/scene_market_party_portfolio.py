"""Portable source-bound cooperative market production portfolio.

Packages a real canonical party checkpoint, replayable save vault and
earned-victory league as one integrity-checked offline deliverable.
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
    export_party, import_party, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_party_league import (
    export_league, import_league, new_league, rank_league,
    record_attempt, verify_league,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    export_vault, import_vault, new_vault, read_slot,
    transact_vault, verify_vault,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _object

SCHEMA = "skeleton.scene_market_party_portfolio.v1"
MAX_BYTES = 2 * 1024 * 1024


def _limit(raw: Any) -> None:
    _bounded(raw, MAX_BYTES)


def pack_portfolio(checkpoint: Any, vault: Any, league: Any,
                   *, slot: str) -> dict[str, Any]:
    party = verify_party(checkpoint)
    saves = verify_vault(vault)
    ranking_source = verify_league(league)
    identity = party["source_digest"]
    if (saves["source_digest"] != identity
            or ranking_source["source_digest"] != identity):
        raise SceneTravelError("cooperative portfolio source mismatch")
    saved = read_slot(saves, slot)
    if saved != party:
        raise SceneTravelError("cooperative portfolio selected save mismatch")
    if party["state"]["market"]["state"]["phase"] != "won":
        raise SceneTravelError("cooperative portfolio requires winning checkpoint")
    if not ranking_source["entries"]:
        raise SceneTravelError("cooperative portfolio requires earned ranked victory")
    if not any(e["party_state_digest"] == party["state_digest"]
               for e in ranking_source["entries"]):
        raise SceneTravelError("cooperative portfolio winning attempt missing")
    party_export = export_party(party)
    vault_export = export_vault(saves)
    league_export = export_league(ranking_source)
    if (import_party(party_export) != party
            or import_vault(vault_export) != saves
            or import_league(league_export) != ranking_source):
        raise SceneTravelError("cooperative portfolio portable replay mismatch")
    result = {"schema_version": SCHEMA,
              "source_digest": identity,
              "party_state_digest": party["state_digest"],
              "vault_state_digest": saves["state_digest"],
              "league_state_digest": ranking_source["state_digest"],
              "slot": slot, "party": party_export,
              "vault": vault_export, "league": league_export,
              "ranking": rank_league(ranking_source),
              "qualification": "offline_replay_bundle_not_signed_release"}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def import_portfolio(raw: Any) -> dict[str, Any]:
    _limit(raw)
    obj = _object(raw, {"schema_version", "source_digest",
                        "party_state_digest", "vault_state_digest",
                        "league_state_digest", "slot", "party", "vault",
                        "league", "ranking", "qualification", "checksum"},
                  "cooperative portfolio")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported cooperative portfolio schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items()
                               if k != "checksum"}):
        raise SceneTravelError("cooperative portfolio checksum mismatch")
    party = import_party(obj["party"])
    vault = import_vault(obj["vault"])
    league = import_league(obj["league"])
    expected = pack_portfolio(party, vault, league, slot=obj["slot"])
    if expected != obj:
        raise SceneTravelError("cooperative portfolio replay mismatch")
    return expected


def accept_portfolio() -> dict[str, Any]:
    source, turns = original_party()
    played = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": played})
    league = record_attempt(new_league(source), "earned-victory", played,
                            expected_revision=0)
    bundle = pack_portfolio(played, vault, league, slot="campaign")
    restored = import_portfolio(json.loads(json.dumps(bundle)))
    if (restored != bundle or restored["ranking"]["ranking"][0]["score"]
            != rank_league(league)["ranking"][0]["score"]):
        raise SceneTravelError("cooperative portfolio acceptance diverged")
    return {"schema_version": "skeleton.scene_market_party_portfolio_acceptance.v1",
            "source_digest": bundle["source_digest"],
            "party_state_digest": bundle["party_state_digest"],
            "portfolio_checksum": bundle["checksum"],
            "phase": played["state"]["market"]["state"]["phase"],
            "turns": len(turns), "ranking": restored["ranking"],
            "qualification": "portable_playable_acceptance_not_device_release"}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-portfolio")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    pack = sub.add_parser("pack")
    pack.add_argument("--checkpoint-json", required=True)
    pack.add_argument("--vault-json", required=True)
    pack.add_argument("--league-json", required=True)
    pack.add_argument("--slot", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command in ("demo", "accept"):
            result = accept_portfolio()
        elif args.command == "pack":
            result = pack_portfolio(_json(args.checkpoint_json),
                                    _json(args.vault_json), _json(args.league_json),
                                    slot=args.slot)
        else:
            result = import_portfolio(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
