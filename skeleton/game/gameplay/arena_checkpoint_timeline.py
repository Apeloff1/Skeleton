"""Replay-verified expedition checkpoints and alternate portable play.

Every historical checkpoint is reconstructed through canonical combat actions.
No caller-supplied currency, inventory, combat result or reward is trusted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_bundle import export_bundle, import_bundle
from skeleton.game.gameplay.arena_expedition import (
    _advance, new_expedition, original_expedition,
    resume_expedition, simulate_expedition, verify_expedition,
)
from skeleton.game.gameplay.arena_expedition_economy import (
    audit_expedition, compare_expeditions,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _parse_json,
)

SCHEMA = "skeleton.arena_checkpoint_timeline.v1"
FORK_SCHEMA = "skeleton.arena_checkpoint_fork.v1"
MAX_BYTES = 2 * 1024 * 1024


def _bounded(payload: Any) -> None:
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            allow_nan=False, ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise CombatSessionError("invalid expedition timeline JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise CombatSessionError("expedition timeline exceeds size budget")


def _replay(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    saved = verify_expedition(payload)
    current = new_expedition(saved["source"])
    checkpoints = [current]
    for event in saved["journal"]:
        current = _advance(current, event["action"])
        if current["journal"][-1] != event:
            raise CombatSessionError("checkpoint history event mismatch")
        checkpoints.append(current)
    if checkpoints[-1] != saved:
        raise CombatSessionError("checkpoint history terminal mismatch")
    return saved, checkpoints


def timeline_expedition(payload: Any) -> dict[str, Any]:
    """Report each actual save, earned accounting and future play position."""
    saved, snapshots = _replay(payload)
    ticks = []
    for snapshot in snapshots:
        audit = audit_expedition(snapshot)
        state = snapshot["state"]
        ticks.append({
            "tick": state["tick"],
            "phase": state["phase"],
            "state_digest": snapshot["state_digest"],
            "save_digest": dig(snapshot["save"]),
            "event_bus_digest": snapshot["event_bus_digest"],
            "hero_hp": state["hero_hp"],
            "currency": state["currency"],
            "inventory": dict(sorted(state["inventory"].items())),
            "next_arena": state["next_index"],
            "economy_checksum": audit["checksum"],
        })
    report = {
        "schema_version": SCHEMA,
        "source_digest": saved["source_digest"],
        "final_state_digest": saved["state_digest"],
        "checkpoints": ticks,
        "count": len(ticks),
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def checkpoint_at(payload: Any, tick: int) -> dict[str, Any]:
    """Export a historical replay checkpoint, including exact save ancestry."""
    saved, snapshots = _replay(payload)
    _integer(tick, "checkpoint tick", 0, len(snapshots) - 1)
    checkpoint = snapshots[tick]
    bundle = export_bundle(checkpoint)
    if import_bundle(bundle) != checkpoint:
        raise CombatSessionError("checkpoint portable roundtrip mismatch")
    if checkpoint["source_digest"] != saved["source_digest"]:
        raise CombatSessionError("checkpoint source mismatch")
    return bundle


def fork_expedition(payload: Any, tick: int, actions: Any) -> dict[str, Any]:
    """Fork a verified checkpoint and compare earned gameplay consequences."""
    saved, snapshots = _replay(payload)
    _integer(tick, "fork tick", 0, len(snapshots) - 1)
    if type(actions) is not list:
        raise CombatSessionError("fork actions must be a list")
    checkpoint = snapshots[tick]
    checkpoint_bundle = checkpoint_at(saved, tick)
    result = resume_expedition(checkpoint, actions)
    result_bundle = export_bundle(result)
    if import_bundle(result_bundle) != result:
        raise CombatSessionError("fork export replay mismatch")
    record = {
        "schema_version": FORK_SCHEMA,
        "original": saved,
        "checkpoint_tick": tick,
        "actions": actions,
        "checkpoint_bundle": checkpoint_bundle,
        "result_bundle": result_bundle,
        "comparison": compare_expeditions(saved, result),
        "source_digest": saved["source_digest"],
        "fork_state_digest": result["state_digest"],
        "fork_economy_checksum": audit_expedition(result)["checksum"],
    }
    record["checksum"] = dig(record)
    _bounded(record)
    return record


def verify_fork(payload: Any) -> dict[str, Any]:
    """Recompute every replay/portable receipt, rejecting altered outcomes."""
    _bounded(payload)
    if type(payload) is not dict or set(payload) != {
        "schema_version", "original", "checkpoint_tick", "actions",
        "checkpoint_bundle", "result_bundle", "comparison",
        "source_digest", "fork_state_digest", "fork_economy_checksum",
        "checksum",
    } or payload["schema_version"] != FORK_SCHEMA:
        raise CombatSessionError("invalid expedition fork record")
    expected = fork_expedition(
        payload["original"], payload["checkpoint_tick"], payload["actions"]
    )
    if payload != expected:
        raise CombatSessionError("expedition fork replay or receipt mismatch")
    return import_bundle(expected["result_bundle"])


def original_fork() -> dict[str, Any]:
    """Original playable route with a real earned consumable branch."""
    source = original_expedition()
    actions = [
        {"kind": "fight"},
        {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"},
        {"kind": "fight"},
    ]
    played = simulate_expedition(source, actions)
    return fork_expedition(played, 1, actions[1:])


def _read_record(raw: str) -> Any:
    """Parse up to 2 MiB with strict duplicate-key and nonfinite rejection."""
    if type(raw) is not str:
        raise CombatSessionError("fork record must be JSON text")
    try:
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise CombatSessionError("fork record exceeds 2 MiB")
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate fork JSON key")
                value[key] = item
            return value
        def nonfinite(_: str) -> Any:
            raise ValueError("nonfinite fork JSON number")
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid fork record JSON") from exc


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.arena_checkpoint_timeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name in ("timeline", "checkpoint", "fork"):
        command = sub.add_parser(name)
        command.add_argument("--session-json", required=True)
        if name != "timeline":
            command.add_argument("--tick", type=int, required=True)
        if name == "fork":
            command.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify-fork")
    verify.add_argument("--record-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_fork()
        elif args.command == "verify-fork":
            final = verify_fork(_read_record(args.record_json))
            result = {
                "ok": True, "source_digest": final["source_digest"],
                "state_digest": final["state_digest"],
                "phase": final["state"]["phase"],
            }
        else:
            session = _parse_json(args.session_json, "expedition save")
            if args.command == "timeline":
                result = timeline_expedition(session)
            elif args.command == "checkpoint":
                result = checkpoint_at(session, args.tick)
            else:
                result = fork_expedition(
                    session, args.tick,
                    _parse_json(args.actions_json, "fork actions"),
                )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
