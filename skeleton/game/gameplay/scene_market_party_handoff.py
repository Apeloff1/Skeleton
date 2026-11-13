"""Replay-verified cooperative campaign handoff across save, league and export.

A handoff is a new offline branch, never an overwrite of the source slot.
It uses the canonical party reducer, vault CAS and earned-victory scorer.
The portable receipt is integrity checked, not a user identity signature.
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
    import_party, original_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_party_timeline import fork_party
from skeleton.game.gameplay.scene_market_party_vault import (
    export_vault, import_vault, new_vault, read_slot, transact_vault, verify_vault,
)
from skeleton.game.gameplay.scene_market_party_league import (
    export_league, import_league, new_league, record_attempt, verify_league,
)
from skeleton.game.gameplay.scene_market_party_portfolio import (
    import_portfolio, pack_portfolio,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_party_handoff.v1"
MAX_BYTES = 8 * 1024 * 1024


def _limit(raw: Any) -> None:
    _bounded(raw, MAX_BYTES)


def _name(value: Any, label: str, max_length: int) -> str:
    name = _id(value, label)
    if len(name) > max_length:
        raise SceneTravelError("cooperative handoff identifier too long")
    return name


def _revision(value: Any, actual: int, label: str) -> None:
    if type(value) is not int or value != actual:
        raise SceneTravelError(f"stale cooperative handoff {label}")


def plan_handoff(vault: Any, league: Any, *, from_slot: str,
                 to_slot: str, sequence: int, turns: Any, attempt_id: str,
                 expected_vault_revision: int,
                 expected_league_revision: int) -> dict[str, Any]:
    """Replay a fork, lease a new slot, rank its victory and export all artifacts.

    Input documents are verified before any operation. No mutation is published
    until all source, save, replay, score and portable checks succeed.
    """
    _limit(vault)
    _limit(league)
    _limit(turns)
    saves = verify_vault(vault)
    rankings = verify_league(league)
    if saves["source_digest"] != rankings["source_digest"]:
        raise SceneTravelError("cooperative handoff source mismatch")
    _revision(expected_vault_revision, saves["revision"], "vault revision")
    _revision(expected_league_revision, rankings["revision"], "league revision")
    source_slot = _name(from_slot, "handoff source slot", 40)
    target_slot = _name(to_slot, "handoff target slot", 40)
    attempt = _name(attempt_id, "handoff attempt id", 48)
    if source_slot == target_slot or target_slot in saves["slots"]:
        raise SceneTravelError("cooperative handoff must create a new save slot")
    parent = read_slot(saves, source_slot)
    proof = fork_party(parent, sequence, turns)
    child = import_party(proof["portable"])
    if child["source_digest"] != saves["source_digest"]:
        raise SceneTravelError("cooperative handoff replay source mismatch")
    if child["state"]["market"]["state"]["phase"] != "won":
        raise SceneTravelError("cooperative handoff requires earned victory")
    next_vault = transact_vault(saves, {
        "kind": "put", "slot": target_slot,
        "expected_revision": expected_vault_revision,
        "expected_slot_digest": None, "checkpoint": child,
    })
    next_league = record_attempt(
        rankings, attempt, child,
        expected_revision=expected_league_revision,
    )
    portfolio = pack_portfolio(child, next_vault, next_league, slot=target_slot)
    portable_vault = export_vault(next_vault)
    portable_league = export_league(next_league)
    if (import_vault(portable_vault) != next_vault
            or import_league(portable_league) != next_league
            or import_portfolio(portfolio) != portfolio):
        raise SceneTravelError("cooperative handoff export replay mismatch")
    result = {
        "schema_version": SCHEMA,
        "source_digest": saves["source_digest"],
        "parent_vault_digest": saves["state_digest"],
        "parent_league_digest": rankings["state_digest"],
        "from_slot": source_slot, "to_slot": target_slot,
        "attempt_id": attempt, "sequence": sequence,
        "turns": turns, "fork_proof": proof,
        "expected_vault_revision": expected_vault_revision,
        "expected_league_revision": expected_league_revision,
        "child_state_digest": child["state_digest"],
        "vault_bundle": portable_vault,
        "league_bundle": portable_league,
        "portfolio": portfolio,
        "qualification": "offline_replayed_handoff_not_authenticated_release",
    }
    result["checksum"] = dig(result)
    _limit(result)
    return result


def verify_handoff(vault: Any, league: Any, receipt: Any) -> dict[str, Any]:
    """Reject forged receipts, changed parents and stale optimistic leases."""
    _limit(receipt)
    obj = _object(receipt, {
        "schema_version", "source_digest", "parent_vault_digest",
        "parent_league_digest", "from_slot", "to_slot", "attempt_id",
        "sequence", "turns", "fork_proof", "expected_vault_revision",
        "expected_league_revision", "child_state_digest", "vault_bundle",
        "league_bundle", "portfolio", "qualification", "checksum",
    }, "cooperative handoff receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported cooperative handoff schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items()
                               if k != "checksum"}):
        raise SceneTravelError("cooperative handoff checksum mismatch")
    expected = plan_handoff(
        vault, league, from_slot=obj["from_slot"], to_slot=obj["to_slot"],
        sequence=obj["sequence"], turns=obj["turns"],
        attempt_id=obj["attempt_id"],
        expected_vault_revision=obj["expected_vault_revision"],
        expected_league_revision=obj["expected_league_revision"],
    )
    if expected != obj:
        raise SceneTravelError("cooperative handoff replay mismatch")
    return expected


def apply_handoff(vault: Any, league: Any, receipt: Any) -> dict[str, Any]:
    """Materialize a verified offline transaction; never mutate parent inputs."""
    approved = verify_handoff(vault, league, receipt)
    saves = import_vault(approved["vault_bundle"])
    ranking = import_league(approved["league_bundle"])
    portfolio = import_portfolio(approved["portfolio"])
    checkpoint = read_slot(saves, approved["to_slot"])
    if (checkpoint["state_digest"] != approved["child_state_digest"]
            or portfolio["party_state_digest"] != checkpoint["state_digest"]):
        raise SceneTravelError("cooperative handoff publication diverged")
    return {"vault": saves, "league": ranking, "portfolio": portfolio,
            "checkpoint": checkpoint, "receipt_checksum": approved["checksum"]}


def accept_handoff() -> dict[str, Any]:
    """Playable source→fork→victory→CAS save→rank→export→reload acceptance."""
    source, turns = original_party()
    played = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": played,
    })
    league = new_league(source)
    midpoint = len(turns) // 2
    receipt = plan_handoff(
        vault, league, from_slot="campaign", to_slot="branch",
        sequence=midpoint, turns=turns[midpoint:],
        attempt_id="branch-win", expected_vault_revision=1,
        expected_league_revision=0,
    )
    restored = apply_handoff(vault, league, json.loads(json.dumps(receipt)))
    if (restored["checkpoint"] != played
            or read_slot(vault, "campaign") != played
            or restored["vault"]["revision"] != 2
            or restored["league"]["revision"] != 1):
        raise SceneTravelError("cooperative handoff acceptance diverged")
    return {"schema_version": "skeleton.scene_market_party_handoff_acceptance.v1",
            "source_digest": receipt["source_digest"],
            "checkpoint_digest": restored["checkpoint"]["state_digest"],
            "receipt_checksum": receipt["checksum"],
            "portfolio_checksum": restored["portfolio"]["checksum"],
            "phase": restored["checkpoint"]["state"]["market"]["state"]["phase"],
            "qualification": "offline_playable_handoff_not_device_release"}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-market-party-handoff")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accept")
    plan = sub.add_parser("plan")
    plan.add_argument("--vault-json", required=True)
    plan.add_argument("--league-json", required=True)
    plan.add_argument("--from-slot", required=True)
    plan.add_argument("--to-slot", required=True)
    plan.add_argument("--sequence", type=int, required=True)
    plan.add_argument("--turns-json", required=True)
    plan.add_argument("--attempt-id", required=True)
    plan.add_argument("--expected-vault-revision", type=int, required=True)
    plan.add_argument("--expected-league-revision", type=int, required=True)
    for command in ("verify", "apply"):
        p = sub.add_parser(command)
        p.add_argument("--vault-json", required=True)
        p.add_argument("--league-json", required=True)
        p.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "accept":
            result = accept_handoff()
        else:
            vault = _json(args.vault_json)
            league = _json(args.league_json)
            if args.command == "plan":
                result = plan_handoff(
                    vault, league, from_slot=args.from_slot,
                    to_slot=args.to_slot, sequence=args.sequence,
                    turns=_json(args.turns_json), attempt_id=args.attempt_id,
                    expected_vault_revision=args.expected_vault_revision,
                    expected_league_revision=args.expected_league_revision,
                )
            else:
                receipt = _json(args.receipt_json)
                result = (verify_handoff(vault, league, receipt)
                          if args.command == "verify" else
                          apply_handoff(vault, league, receipt))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
