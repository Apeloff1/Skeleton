"""Portable original combat-mission distribution with replayed acceptance.

A package contains a playable source, its earned completion route, canonical
save and a bounded rights *declaration*. It does not authenticate publishers,
license rights, device qualification or marketplace approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _object, _parse_json, original_demo,
)
from skeleton.game.gameplay.combat_contract import (
    MAX_SESSION_BYTES, _bounded, export_contract, import_contract,
    normalize_contract, original_contract, simulate_contract,
)

SCHEMA = "skeleton.combat_contract_package.v1"
MAX_ACTIONS = 64
MAX_BYTES = 2 * 1024 * 1024
RIGHTS_DECLARATIONS = frozenset((
    "original_self_authored", "licensed_with_permission",
))


def normalize_metadata(raw: Any) -> dict[str, str]:
    obj = _object(raw, {
        "package_id", "title", "publisher_id", "rights_declaration",
    }, "combat package metadata")
    package_id = _id(obj["package_id"], "package_id")
    publisher = _id(obj["publisher_id"], "publisher_id")
    title = obj["title"]
    if (type(title) is not str or not 1 <= len(title) <= 120
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in title)
            or title != title.strip()):
        raise CombatSessionError("invalid package title")
    rights = obj["rights_declaration"]
    if type(rights) is not str or rights not in RIGHTS_DECLARATIONS:
        raise CombatSessionError("unsupported rights declaration")
    return {
        "package_id": package_id, "title": title,
        "publisher_id": publisher, "rights_declaration": rights,
    }


def build_package(source: Any, actions: Any, metadata: Any) -> dict[str, Any]:
    spec = normalize_contract(source)
    meta = normalize_metadata(metadata)
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
        raise CombatSessionError("invalid package action budget")
    _bounded(actions, MAX_SESSION_BYTES)
    saved = simulate_contract(spec, actions)
    if saved["state"]["phase"] != "won":
        raise CombatSessionError("package has no earned playable victory")
    canonical_actions = [event["action"] for event in saved["journal"]]
    if canonical_actions != actions:
        raise CombatSessionError("noncanonical package actions")
    portable = export_contract(saved)
    if import_contract(portable) != saved:
        raise CombatSessionError("package portable save mismatch")
    manifest = {
        "schema_version": SCHEMA,
        "metadata": meta,
        "world_id": spec["scenario"]["world_id"],
        "contract_id": spec["contract_id"],
        "source_digest": dig(spec),
        "state_digest": saved["state_digest"],
        "action_count": len(canonical_actions),
        "earned_credits": saved["state"]["credits"],
        "earned_inventory": saved["state"]["inventory"],
    }
    manifest["digest"] = dig(manifest)
    package = {
        "schema_version": SCHEMA,
        "manifest": manifest,
        "source": spec,
        "actions": canonical_actions,
        "portable_save": portable,
    }
    package["checksum"] = dig(package)
    _bounded(package, MAX_BYTES)
    return package


def verify_package(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "manifest", "source", "actions",
        "portable_save", "checksum",
    }, "combat game package")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported combat game package schema")
    manifest = _object(obj["manifest"], {
        "schema_version", "metadata", "world_id", "contract_id",
        "source_digest", "state_digest", "action_count",
        "earned_credits", "earned_inventory", "digest",
    }, "combat package manifest")
    expected = build_package(
        obj["source"], obj["actions"], manifest["metadata"],
    )
    if expected != obj:
        raise CombatSessionError("combat game package replay mismatch")
    return expected


def play_package(raw: Any) -> dict[str, Any]:
    package = verify_package(raw)
    session = import_contract(package["portable_save"])
    if session["state"]["phase"] != "won":
        raise CombatSessionError("packaged game has no earned victory")
    return session


def original_package() -> dict[str, Any]:
    _, actions = original_demo()
    return build_package(original_contract(), actions, {
        "package_id": "bridge_watch_original",
        "title": "Bridge Watch: Lantern Crossing",
        "publisher_id": "skeleton_original",
        "rights_declaration": "original_self_authored",
    })


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-contract-package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    build = sub.add_parser("build")
    build.add_argument("--source-json", required=True)
    build.add_argument("--actions-json", required=True)
    build.add_argument("--metadata-json", required=True)
    for command in ("verify", "play"):
        sub.add_parser(command).add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_package()
        elif args.command == "build":
            result = build_package(
                _parse_json(args.source_json, "package source"),
                _parse_json(args.actions_json, "package actions"),
                _parse_json(args.metadata_json, "package metadata"),
            )
        else:
            package = _parse_json(args.package_json, "game package")
            result = (verify_package(package) if args.command == "verify"
                      else play_package(package))
        _bounded(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
