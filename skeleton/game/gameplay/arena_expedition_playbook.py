"""Portable offline expedition playbook: authored route -> verified ending.

Connects the canonical combat engine, bounded planner, economy audit and
portable save importer. Every import reconstructs the complete route.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_bundle import export_bundle, import_bundle
from skeleton.game.gameplay.arena_expedition import (
    new_expedition, original_expedition, resume_expedition, verify_expedition,
)
from skeleton.game.gameplay.arena_expedition_economy import (
    audit_expedition, verify_audit,
)
from skeleton.game.gameplay.arena_expedition_solver import (
    plan_expedition, verify_plan,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json,
)

SCHEMA = "skeleton.arena_expedition_playbook.v1"
MAX_BYTES = 512 * 1024


def _bound(value: Any) -> None:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid expedition playbook JSON") from exc
    if len(data) > MAX_BYTES:
        raise CombatSessionError("expedition playbook size budget exceeded")


def build_playbook(source: Any = None, *, session: Any = None,
                   actions: Any = None, max_states: int = 128,
                   max_depth: int = 16) -> dict[str, Any]:
    """Build a complete portable artifact from a source or verified save.

    Manual actions are allowed but still executed through the canonical
    engine. Automatic actions require a found, replay-verified solver witness.
    No game rewards or terminal state can be supplied by the caller.
    """
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one playbook source or save")
    initial = new_expedition(source) if session is None else verify_expedition(session)
    if actions is None:
        plan = plan_expedition(
            session=initial, max_states=max_states, max_depth=max_depth,
        )
        if plan["status"] != "found":
            raise CombatSessionError(
                "expedition playbook has no proven victory within search budget"
            )
        actions = plan["actions"]
        verify_plan(plan, session=initial)
    else:
        plan = None
        if type(actions) is not list:
            raise CombatSessionError("invalid playbook action list")
    final = resume_expedition(initial, actions)
    if final["state"]["phase"] != "won":
        raise CombatSessionError("expedition playbook requires an earned victory")
    bundle = export_bundle(final)
    audit = audit_expedition(final)
    record = {
        "schema_version": SCHEMA,
        "source_digest": initial["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "final_state_digest": final["state_digest"],
        "initial": initial,
        "actions": actions,
        "plan": plan,
        "audit": audit,
        "bundle": bundle,
    }
    record["checksum"] = dig(record)
    _bound(record)
    return record


def import_playbook(payload: Any) -> dict[str, Any]:
    """Reject forged route, source, rewards, audit or portable game bundle."""
    _bound(payload)
    keys = {
        "schema_version", "source_digest", "initial_state_digest",
        "final_state_digest", "initial", "actions", "plan",
        "audit", "bundle", "checksum",
    }
    if (
        type(payload) is not dict or set(payload) != keys
        or payload["schema_version"] != SCHEMA
    ):
        raise CombatSessionError("invalid expedition playbook fields")
    checksum = payload["checksum"]
    if type(checksum) is not str or len(checksum) != 64:
        raise CombatSessionError("invalid expedition playbook checksum")
    if dig({k: v for k, v in payload.items() if k != "checksum"}) != checksum:
        raise CombatSessionError("expedition playbook checksum mismatch")
    initial = verify_expedition(payload["initial"])
    if (
        initial["source_digest"] != payload["source_digest"]
        or initial["state_digest"] != payload["initial_state_digest"]
    ):
        raise CombatSessionError("expedition playbook initial source mismatch")
    actions = payload["actions"]
    if type(actions) is not list:
        raise CombatSessionError("invalid expedition playbook actions")
    plan = payload["plan"]
    if plan is not None:
        verified = verify_plan(plan, session=initial)
        if verified["status"] != "found" or verified["actions"] != actions:
            raise CombatSessionError("expedition playbook solver witness mismatch")
    final = resume_expedition(initial, actions)
    if (
        final["state"]["phase"] != "won"
        or final["state_digest"] != payload["final_state_digest"]
    ):
        raise CombatSessionError("expedition playbook terminal replay mismatch")
    if import_bundle(payload["bundle"]) != final:
        raise CombatSessionError("expedition playbook bundle mismatch")
    verify_audit(payload["audit"], session=final)
    return final


def original_playbook() -> dict[str, Any]:
    """Original source and earned actions, not a fabricated winning state."""
    return build_playbook(original_expedition(), actions=[
        {"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"},
    ])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-expedition-playbook")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Build original offline verified victory artifact")
    for name, fields in {
        "build": ("source-json", "actions-json"),
        "solve": ("source-json",),
        "resume": ("session-json", "actions-json"),
        "verify": ("playbook-json",),
    }.items():
        command = sub.add_parser(name)
        for field in fields:
            command.add_argument("--" + field, required=True)
    args = parser.parse_args(list(argv))
    try:
        def read(name: str) -> Any:
            return _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            result = original_playbook()
        elif args.command == "build":
            result = build_playbook(
                read("source-json"), actions=read("actions-json"),
            )
        elif args.command == "solve":
            result = build_playbook(read("source-json"))
        elif args.command == "resume":
            result = build_playbook(
                session=read("session-json"), actions=read("actions-json"),
            )
        else:
            final = import_playbook(read("playbook-json"))
            result = {
                "ok": True, "source_digest": final["source_digest"],
                "state_digest": final["state_digest"],
                "phase": final["state"]["phase"],
            }
        _bound(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
