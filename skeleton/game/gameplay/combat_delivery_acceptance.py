"""Cross-verified original combat game delivery: package and playable acceptance.

The source, winning replay, earned inventory, portable save, rights declaration
and acceptance must agree. This proves functional consistency, not publisher
identity, legal rights, device support or marketplace approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_contract import (
    _bounded, original_contract,
)
from skeleton.game.gameplay.combat_contract_package import (
    build_package, original_package, play_package, verify_package,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.game_vertical_acceptance import (
    accept_vertical, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_delivery_acceptance.v1"
MAX_BYTES = 4 * 1024 * 1024


def build_delivery(source: Any, actions: Any,
                   metadata: Any) -> dict[str, Any]:
    package = build_package(source, actions, metadata)
    acceptance = accept_vertical(
        "combat_contract", package["source"], package["actions"])
    manifest = package["manifest"]
    if (acceptance["source_digest"] != manifest["source_digest"]
            or acceptance["state_digest"] != manifest["state_digest"]
            or acceptance["portable_bundle"] != package["portable_save"]):
        raise CombatSessionError("combat package and acceptance disagree")
    delivered = {
        "schema_version": SCHEMA,
        "package": package, "acceptance": acceptance,
        "manifest_digest": manifest["digest"],
        "source_digest": manifest["source_digest"],
        "state_digest": manifest["state_digest"],
    }
    delivered["receipt"] = dig(delivered)
    _bounded(delivered, MAX_BYTES)
    return delivered


def verify_delivery(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "package", "acceptance",
        "manifest_digest", "source_digest", "state_digest", "receipt",
    }, "combat delivery receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported combat delivery schema")
    package = verify_package(obj["package"])
    accepted = verify_acceptance(obj["acceptance"])
    if (accepted["kind"] != "combat_contract"
            or accepted["source_digest"] != package["manifest"]["source_digest"]
            or accepted["state_digest"] != package["manifest"]["state_digest"]
            or accepted["portable_bundle"] != package["portable_save"]):
        raise CombatSessionError("combat delivery lineage mismatch")
    expected = build_delivery(
        package["source"], package["actions"],
        package["manifest"]["metadata"])
    if expected != obj:
        raise CombatSessionError("combat delivery replay mismatch")
    return expected


def play_delivery(raw: Any) -> dict[str, Any]:
    delivered = verify_delivery(raw)
    final = play_package(delivered["package"])
    if (final["state_digest"] != delivered["state_digest"]
            or final["state"]["phase"] != "won"):
        raise CombatSessionError("delivered combat game not playable")
    return {
        "ok": True,
        "contract_id": final["source"]["contract_id"],
        "state_digest": final["state_digest"],
        "credits": final["state"]["credits"],
        "inventory": final["state"]["inventory"],
        "phase": final["state"]["phase"],
    }


def original_delivery() -> dict[str, Any]:
    package = original_package()
    return build_delivery(
        original_contract(), package["actions"],
        package["manifest"]["metadata"])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton combat-delivery-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    build = sub.add_parser("build")
    build.add_argument("--source-json", required=True)
    build.add_argument("--actions-json", required=True)
    build.add_argument("--metadata-json", required=True)
    for command in ("verify", "play"):
        sub.add_parser(command).add_argument("--delivery-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_delivery()
        elif args.command == "build":
            result = build_delivery(
                _parse_json(args.source_json, "delivery source"),
                _parse_json(args.actions_json, "delivery actions"),
                _parse_json(args.metadata_json, "delivery metadata"))
        else:
            delivery = _parse_json(args.delivery_json, "delivery receipt")
            result = (
                verify_delivery(delivery) if args.command == "verify"
                else play_delivery(delivery))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
