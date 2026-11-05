"""End-to-end replay evidence for playable faction quest verticals.

This proves a specific authored source/action trace can reach an earned
ending, be checkpointed and exported. It is not device or release approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_ACTIONS, demo_actions
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_factions import (
    MAX_BYTES, _bounded, export_factions, import_factions, new_factions,
    original_factions, resume_factions, verify_factions,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _object, _parse_json,
)

SCHEMA = "skeleton.quest_factions_acceptance.v1"


def accept_vertical(source: Any, actions: Any, *,
                    expected_ending: str | None = None) -> dict[str, Any]:
    """Replay every prefix and require identical checkpoint/resume behavior."""
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
        raise CombatSessionError("invalid faction acceptance action trace")
    if expected_ending is not None:
        expected_ending = _id(expected_ending, "expected_ending")
    current = new_factions(source)
    checkpoint_digests = [current["state_digest"]]
    canonical_actions = []
    for action in actions:
        # Every intermediate checkpoint is independently reconstructed from
        # the initial source and canonical actions, not trusted from caller.
        current = resume_factions(current, [action])
        canonical_actions.append(current["journal"][-1]["action"])
        replay = resume_factions(new_factions(source), canonical_actions)
        if replay != current:
            raise CombatSessionError("faction checkpoint/resume divergence")
        checkpoint_digests.append(current["state_digest"])
    saved = verify_factions(current)
    if saved["state"]["phase"] != "finished":
        raise CombatSessionError("faction acceptance requires earned finished ending")
    ending = saved["state"]["ending"]
    if expected_ending is not None and ending != expected_ending:
        raise CombatSessionError("faction acceptance ending mismatch")
    bundle = export_factions(saved)
    if import_factions(bundle) != saved:
        raise CombatSessionError("faction acceptance portable replay mismatch")
    quest = saved["state"]["quest"]["state"]
    report = {
        "schema_version": SCHEMA,
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "event_bus_digest": saved["event_bus_digest"],
        "ending": ending,
        "phase": saved["state"]["phase"],
        "standing": dict(sorted(saved["state"]["standing"].items())),
        "npc_choices": dict(sorted(quest["choices"].items())),
        "crafted": list(quest["crafted"]),
        "inventory": dict(sorted(quest["items"].items())),
        "combat_phase": quest["expedition"]["state"]["phase"],
        "earned_currency_balance": quest["expedition"]["state"]["currency"],
        "checkpoint_digests": checkpoint_digests,
        "actions": canonical_actions,
        "portable_checksum": bundle["checksum"],
    }
    report["checksum"] = dig(report)
    _bounded(report, MAX_BYTES)
    return report


def verify_acceptance(raw: Any, *, source: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest",
        "event_bus_digest", "ending", "phase", "standing", "npc_choices",
        "crafted", "inventory", "combat_phase", "earned_currency_balance",
        "checkpoint_digests", "actions", "portable_checksum", "checksum",
    }, "faction acceptance receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported faction acceptance receipt")
    rebuilt = accept_vertical(
        source, obj["actions"], expected_ending=obj["ending"],
    )
    if rebuilt != obj:
        raise CombatSessionError("faction acceptance evidence mismatch")
    return rebuilt


def original_acceptance_demo() -> dict[str, Any]:
    return accept_vertical(
        original_factions(), demo_actions(), expected_ending="beacon_lit",
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-factions-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    accept = sub.add_parser("accept")
    accept.add_argument("--source-json", required=True)
    accept.add_argument("--actions-json", required=True)
    accept.add_argument("--ending-id")
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_acceptance_demo()
        elif args.command == "accept":
            result = accept_vertical(
                _parse_json(args.source_json, "faction source"),
                _parse_json(args.actions_json, "faction actions"),
                expected_ending=args.ending_id,
            )
        else:
            result = verify_acceptance(
                _parse_json(args.receipt_json, "faction acceptance receipt"),
                source=_parse_json(args.source_json, "faction source"),
            )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("faction acceptance CLI output exceeds size budget")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
