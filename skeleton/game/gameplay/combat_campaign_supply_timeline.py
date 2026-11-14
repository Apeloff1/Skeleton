"""Replay-derived supply combat checkpoints, economy and branch custody.

All changes are replayed by the canonical campaign engine. Receipts are
integrity checks, never signatures, rights or authorization claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_supply import (
    MAX_COMMANDS, _advance, _encoded, new_supply, original_supply,
    verify_supply, finish_supply,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _object, _parse_json,
)

TIMELINE = "skeleton.combat_supply_timeline.v1"
FORK = "skeleton.combat_supply_fork.v1"
PACKAGE = "skeleton.combat_supply_timeline_package.v1"
COMPARE = "skeleton.combat_supply_branch_compare.v1"


def _prefix(session: dict[str, Any], count: int) -> dict[str, Any]:
    current = new_supply(session["source"])
    for action in session["state"]["journal"][:count]:
        current = _advance(current, action)
    return current


def checkpoint_supply(raw: Any, index: Any) -> dict[str, Any]:
    saved = verify_supply(raw)
    count = _integer(index, "checkpoint index", 0, len(saved["state"]["journal"]))
    return verify_supply(_prefix(saved, count))


def timeline_supply(raw: Any) -> dict[str, Any]:
    saved = verify_supply(raw)
    current = new_supply(saved["source"])
    steps = []
    earned = spent = 0
    for action in saved["state"]["journal"]:
        after = _advance(current, action)
        old, new = current["state"], after["state"]
        delta = new["currency"] - old["currency"]
        credit = delta if action["kind"] == "fight" else 0
        debit = -delta if action["kind"] == "buy" else 0
        if credit < 0 or debit < 0 or delta != credit - debit:
            raise CombatSessionError("supply accounting reconciliation mismatch")
        if action["kind"] == "buy" and debit != saved["source"]["prices"][action["item"]]:
            raise CombatSessionError("supply purchase price mismatch")
        if action["kind"] == "fight":
            if len(new["battles"]) != len(old["battles"]) + 1:
                raise CombatSessionError("missing canonical battle")
            if new["battles"][-1]["combat"]["state"]["currency"] != credit:
                raise CombatSessionError("combat reward reconciliation mismatch")
        elif len(new["battles"]) != len(old["battles"]):
            raise CombatSessionError("noncombat command changed battle count")
        entry = {
            "index": len(new["journal"]), "command": action,
            "before": current["state_digest"], "after": after["state_digest"],
            "save_digest": dig(after["save"]),
            "phase": new["phase"], "hp": new["hp"],
            "hp_delta": new["hp"] - old["hp"],
            "currency": new["currency"], "earned": credit, "spent": debit,
            "inventory_delta": {
                item: new["inventory"][item] - old["inventory"][item]
                for item in ("medkit", "ward")
                if new["inventory"][item] != old["inventory"][item]
            },
            "ward_active": new["ward_active"],
            "encounters_completed": len(new["battles"]),
        }
        entry["receipt"] = dig(entry)
        steps.append(entry)
        earned += credit
        spent += debit
        current = after
    if current != saved or earned - spent != saved["state"]["currency"]:
        raise CombatSessionError("supply timeline replay mismatch")
    result = {
        "schema_version": TIMELINE, "claim": "offline_integrity_only",
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "save_digest": dig(saved["save"]),
        "initial_state_digest": new_supply(saved["source"])["state_digest"],
        "phase": saved["state"]["phase"],
        "total_earned": earned, "total_spent": spent,
        "balance": saved["state"]["currency"],
        "inventory": dict(saved["state"]["inventory"]),
        "hp": saved["state"]["hp"], "steps": steps,
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_timeline(raw: Any, *, session: Any) -> dict[str, Any]:
    expected = timeline_supply(session)
    if type(raw) is not dict or raw != expected:
        raise CombatSessionError("supply timeline replay mismatch")
    return expected


def fork_supply(raw: Any, index: Any, suffix: Any) -> dict[str, Any]:
    origin = verify_supply(raw)
    count = _integer(index, "checkpoint index", 0, len(origin["state"]["journal"]))
    if type(suffix) is not list or len(suffix) > MAX_COMMANDS - count:
        raise CombatSessionError("invalid bounded supply suffix")
    checkpoint = _prefix(origin, count)
    branch = checkpoint
    for action in suffix:
        branch = _advance(branch, action)
    branch = verify_supply(branch)
    record = {
        "schema_version": FORK, "claim": "offline_integrity_only",
        "source_digest": origin["source_digest"],
        "origin_state_digest": origin["state_digest"],
        "checkpoint_index": count,
        "checkpoint_state_digest": checkpoint["state_digest"],
        "branch_state_digest": branch["state_digest"],
        "suffix": suffix, "origin": origin, "branch": branch,
    }
    record["receipt"] = dig(record)
    _encoded(record)
    return record


def verify_fork(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "claim", "source_digest", "origin_state_digest",
        "checkpoint_index", "checkpoint_state_digest", "branch_state_digest",
        "suffix", "origin", "branch", "receipt",
    }, "supply fork")
    if obj["schema_version"] != FORK or obj["claim"] != "offline_integrity_only":
        raise CombatSessionError("unsupported supply fork schema")
    _encoded(obj)
    expected = fork_supply(obj["origin"], obj["checkpoint_index"], obj["suffix"])
    if obj != expected:
        raise CombatSessionError("supply fork lineage mismatch")
    return expected


def compare_supply(left: Any, right: Any) -> dict[str, Any]:
    lhs, rhs = verify_supply(left), verify_supply(right)
    if lhs["source_digest"] != rhs["source_digest"]:
        raise CombatSessionError("supply branches have different authored sources")
    common = 0
    for a, b in zip(lhs["state"]["journal"], rhs["state"]["journal"]):
        if a != b:
            break
        common += 1
    shared = _prefix(lhs, common)
    def summary(session: dict[str, Any]) -> dict[str, Any]:
        state = session["state"]
        return {
            "state_digest": session["state_digest"],
            "save_digest": dig(session["save"]),
            "commands": len(state["journal"]),
            "phase": state["phase"], "hp": state["hp"],
            "currency": state["currency"], "inventory": dict(state["inventory"]),
            "ward_active": state["ward_active"],
            "encounters_completed": len(state["battles"]),
        }
    result = {
        "schema_version": COMPARE, "claim": "offline_integrity_only",
        "source_digest": lhs["source_digest"],
        "common_commands": common,
        "shared_checkpoint_state_digest": shared["state_digest"],
        "same_state": lhs["state_digest"] == rhs["state_digest"],
        "left": summary(lhs), "right": summary(rhs),
        "hp_delta_right_minus_left": rhs["state"]["hp"] - lhs["state"]["hp"],
        "currency_delta_right_minus_left": (
            rhs["state"]["currency"] - lhs["state"]["currency"]
        ),
        "inventory_delta_right_minus_left": {
            item: rhs["state"]["inventory"][item] - lhs["state"]["inventory"][item]
            for item in ("medkit", "ward")
        },
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def package_timeline(raw: Any) -> dict[str, Any]:
    saved = verify_supply(raw)
    package = {
        "schema_version": PACKAGE, "claim": "offline_integrity_only",
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "session": saved, "timeline": timeline_supply(saved),
    }
    package["receipt"] = dig(package)
    _encoded(package)
    return package


def import_timeline(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "claim", "source_digest", "state_digest",
        "session", "timeline", "receipt",
    }, "supply timeline package")
    if obj["schema_version"] != PACKAGE or obj["claim"] != "offline_integrity_only":
        raise CombatSessionError("unsupported supply timeline package")
    _encoded(obj)
    expected = package_timeline(obj["session"])
    if obj != expected:
        raise CombatSessionError("supply timeline package replay mismatch")
    return verify_supply(expected["session"])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-supply-timeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Replay the original offline combat supply game")
    for name in ("timeline", "package"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    at = sub.add_parser("checkpoint")
    at.add_argument("--session-json", required=True)
    at.add_argument("--index", type=int, required=True)
    fork = sub.add_parser("fork")
    fork.add_argument("--session-json", required=True)
    fork.add_argument("--index", type=int, required=True)
    fork.add_argument("--actions-json", required=True)
    sub.add_parser("verify-fork").add_argument("--fork-json", required=True)
    comp = sub.add_parser("compare")
    comp.add_argument("--left-json", required=True)
    comp.add_argument("--right-json", required=True)
    sub.add_parser("import").add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = timeline_supply(finish_supply(original_supply()))
        elif args.command == "timeline":
            result = timeline_supply(_parse_json(args.session_json, "supply save"))
        elif args.command == "checkpoint":
            result = checkpoint_supply(
                _parse_json(args.session_json, "supply save"), args.index,
            )
        elif args.command == "fork":
            result = fork_supply(
                _parse_json(args.session_json, "supply save"), args.index,
                _parse_json(args.actions_json, "supply suffix"),
            )
        elif args.command == "verify-fork":
            result = verify_fork(_parse_json(args.fork_json, "supply fork"))
        elif args.command == "compare":
            result = compare_supply(
                _parse_json(args.left_json, "left supply save"),
                _parse_json(args.right_json, "right supply save"),
            )
        elif args.command == "package":
            result = package_timeline(_parse_json(args.session_json, "supply save"))
        else:
            result = import_timeline(_parse_json(args.package_json, "supply package"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
