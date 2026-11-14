"""End-to-end original combat supply acceptance with source-bound replay proofs.

The acceptance CLI actually edits authored content, plays canonical combat,
buys/uses earned inventory, restores saves and checks portable export.
It is a deterministic fixture, not a replacement for CI or device testing.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_supply import (
    _encoded, advance_supply, new_supply, normalize_supply, original_supply,
    package_supply, verify_supply, verify_supply_package,
)
from skeleton.game.gameplay.combat_campaign_supply_author import (
    author_supply, verify_supply_authoring,
)
from skeleton.game.gameplay.combat_campaign_supply_solver import (
    solve_supply, verify_supply_solution,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_supply_acceptance.v1"


def accept_original_supply() -> dict[str, Any]:
    original = original_supply()
    authored = author_supply(original, [
        {"kind": "set-price", "item": "medkit", "value": 6},
        {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12},
    ], dig(normalize_supply(original)))
    verify_supply_authoring(original, authored)
    source = authored["source"]
    session = new_supply(source)
    first = advance_supply(session, {"kind": "fight"})
    checkpoint = verify_supply(json.loads(_encoded(first)))
    bought = advance_supply(checkpoint, {"kind": "buy", "item": "medkit"})
    healed = advance_supply(bought, {"kind": "use", "item": "medkit"})
    final = advance_supply(healed, {"kind": "fight"})
    if final["state"]["phase"] != "won":
        raise CombatSessionError("acceptance original campaign did not win")
    if final["state"]["hp"] <= first["state"]["hp"] - 2:
        raise CombatSessionError("acceptance medkit had no gameplay benefit")
    restored = verify_supply(json.loads(_encoded(final)))
    if restored != final:
        raise CombatSessionError("acceptance save replay drift")
    portable = package_supply(restored)
    if verify_supply_package(json.loads(_encoded(portable))) != portable:
        raise CombatSessionError("acceptance portable replay drift")
    route = solve_supply(source, min_hp=10, max_states=96, max_depth=12)
    if route["status"] != "found":
        raise CombatSessionError("acceptance supply route not found")
    verify_supply_solution(source, route)
    result = {
        "schema_version": SCHEMA,
        "claim": "offline_fixture_acceptance_only",
        "original_source_digest": dig(normalize_supply(original)),
        "authored_source_digest": dig(source),
        "author_receipt": authored["receipt"],
        "first_checkpoint_digest": checkpoint["state_digest"],
        "final_state_digest": final["state_digest"],
        "final_save_digest": dig(final["save"]),
        "portable_digest": portable["digest"],
        "solver_receipt": route["receipt"],
        "phase": final["state"]["phase"],
        "hp": final["state"]["hp"],
        "currency": final["state"]["currency"],
        "commands": final["state"]["journal"],
        "battles": len(final["state"]["battles"]),
        "source_unchanged": original == original_supply(),
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_supply_acceptance(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "claim", "original_source_digest",
        "authored_source_digest", "author_receipt",
        "first_checkpoint_digest", "final_state_digest",
        "final_save_digest", "portable_digest", "solver_receipt",
        "phase", "hp", "currency", "commands", "battles",
        "source_unchanged", "receipt",
    }, "supply acceptance")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_fixture_acceptance_only":
        raise CombatSessionError("unsupported supply acceptance schema")
    _encoded(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("supply acceptance receipt digest mismatch")
    expected = accept_original_supply()
    if expected != obj:
        raise CombatSessionError("supply acceptance replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-supply-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run full offline supply vertical acceptance")
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_original_supply()
        else:
            result = verify_supply_acceptance(
                _parse_json(args.receipt_json, "supply acceptance"),
            )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
