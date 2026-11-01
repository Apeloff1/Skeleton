"""End-to-end playable acceptance for original quest and tactical forge games.

Acceptance is derived by executing canonical gameplay, checking deterministic
checkpoint replay and importing the actual portable save. It is not a device,
publisher, provenance, authorization or release certificate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _object, _parse_json

SCHEMA = "skeleton.game_vertical_acceptance.v1"
BUNDLE = "skeleton.game_vertical_acceptance_bundle.v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_ACTIONS = 96


def _bounded(value: Any) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid acceptance JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise CombatSessionError("acceptance byte budget exceeded")


def _engine(kind: Any):
    if kind == "quest":
        from skeleton.game.gameplay.quest_chapter_campaign import (
            simulate_campaign, resume_campaign, verify_campaign,
            export_campaign, import_campaign,
        )
        return (simulate_campaign, resume_campaign, verify_campaign,
                export_campaign, import_campaign)
    if kind == "combat_contract":
        from skeleton.game.gameplay.combat_contract import (
            simulate_contract, resume_contract, verify_contract,
            export_contract, import_contract,
        )
        return (simulate_contract, resume_contract, verify_contract,
                export_contract, import_contract)
    if kind == "expedition_quest":
        from skeleton.game.gameplay.expedition_quest import (
            simulate_quest, resume_quest, verify_quest,
            export_quest, import_quest,
        )
        return (simulate_quest, resume_quest, verify_quest,
                export_quest, import_quest)
    if kind == "forge":
        from skeleton.game.gameplay.arena_forge_run import (
            simulate_forge, resume_forge, verify_forge, export_forge, import_forge,
        )
        return (simulate_forge, resume_forge, verify_forge,
                export_forge, import_forge)
    raise CombatSessionError("unsupported playable acceptance kind")


def accept_vertical(kind: str, source: Any, actions: Any, *,
                    checkpoint_at: int | None = None) -> dict[str, Any]:
    """Prove authored source -> play -> checkpoint -> replay -> portable import."""
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise CombatSessionError("invalid acceptance action budget")
    if checkpoint_at is None:
        checkpoint_at = len(actions) // 2
    if (type(checkpoint_at) is not int
            or not 0 <= checkpoint_at <= len(actions)):
        raise CombatSessionError("invalid acceptance checkpoint boundary")
    _bounded(source)
    _bounded(actions)
    simulate, resume, verify, export, import_save = _engine(kind)
    full = simulate(source, actions)
    checkpoint = simulate(source, actions[:checkpoint_at])
    replayed = resume(checkpoint, actions[checkpoint_at:])
    if replayed != full or verify(full) != full:
        raise CombatSessionError("playable checkpoint replay mismatch")
    portable = export(full)
    imported = import_save(portable)
    if imported != full:
        raise CombatSessionError("portable save round-trip mismatch")
    if kind == "expedition_quest":
        if full["state"]["phase"] != "finished":
            raise CombatSessionError("playable quest has no earned ending")
        phase = full["state"]["expedition"]["state"]["phase"]
    else:
        phase = full["state"]["phase"]
    if phase != "won":
        raise CombatSessionError("playable vertical has no earned victory")
    report = {
        "schema_version": SCHEMA, "kind": kind,
        "source": full["source"], "actions": actions,
        "checkpoint_at": checkpoint_at,
        "source_digest": full["source_digest"],
        "state_digest": full["state_digest"],
        "checkpoint_digest": dig(checkpoint),
        "save_digest": dig(full["save"]),
        "phase": phase,
        "portable_bundle": portable,
    }
    report["receipt"] = dig(report)
    _bounded(report)
    return report


def verify_acceptance(payload: Any) -> dict[str, Any]:
    """Re-execute all gameplay; never trust a caller-supplied victory receipt."""
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "kind", "source", "actions", "checkpoint_at",
        "source_digest", "state_digest", "checkpoint_digest", "save_digest",
        "phase", "portable_bundle", "receipt",
    }, "playable acceptance")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported playable acceptance schema")
    expected = accept_vertical(
        obj["kind"], obj["source"], obj["actions"],
        checkpoint_at=obj["checkpoint_at"],
    )
    if obj != expected:
        raise CombatSessionError("playable acceptance replay mismatch")
    return expected


def export_acceptance(payload: Any) -> dict[str, Any]:
    report = verify_acceptance(payload)
    record = {
        "schema_version": BUNDLE, "kind": report["kind"],
        "source_digest": report["source_digest"],
        "state_digest": report["state_digest"],
        "acceptance": report,
    }
    record["checksum"] = dig(record)
    _bounded(record)
    return record


def import_acceptance(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "kind", "source_digest", "state_digest",
        "acceptance", "checksum",
    }, "playable acceptance bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported acceptance bundle schema")
    if (type(obj["checksum"]) is not str
            or obj["checksum"] != dig({
                k: v for k, v in obj.items() if k != "checksum"
            })):
        raise CombatSessionError("acceptance bundle checksum mismatch")
    report = verify_acceptance(obj["acceptance"])
    if (obj["kind"] != report["kind"]
            or obj["source_digest"] != report["source_digest"]
            or obj["state_digest"] != report["state_digest"]):
        raise CombatSessionError("acceptance bundle source/state mismatch")
    return report


def demo_acceptance(kind: str) -> dict[str, Any]:
    if kind == "quest":
        from skeleton.game.gameplay.quest_chapter_campaign import (
            original_campaign, demo_campaign_actions,
        )
        return accept_vertical(kind, original_campaign(), demo_campaign_actions())
    if kind == "combat_contract":
        from skeleton.game.gameplay.combat_contract import original_contract
        from skeleton.game.gameplay.turn_combat import original_demo
        _, actions = original_demo()
        return accept_vertical(kind, original_contract(), actions)
    if kind == "expedition_quest":
        from skeleton.game.gameplay.expedition_quest import (
            original_quest, demo_actions,
        )
        return accept_vertical(kind, original_quest(), demo_actions())
    if kind == "forge":
        from skeleton.game.gameplay.arena_forge_run import original_forge
        return accept_vertical(kind, original_forge(), [
            {"kind": "fight"}, {"kind": "craft", "recipe_id": "tide_edge"},
            {"kind": "equip", "recipe_id": "tide_edge"}, {"kind": "fight"},
        ])
    raise CombatSessionError("unsupported playable acceptance kind")


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton game-vertical-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--kind", choices=("forge", "quest", "expedition_quest", "combat_contract"), required=True)
    run = sub.add_parser("run")
    run.add_argument("--kind", choices=("forge", "quest", "expedition_quest", "combat_contract"), required=True)
    run.add_argument("--source-json", required=True)
    run.add_argument("--actions-json", required=True)
    run.add_argument("--checkpoint-at", type=int)
    for name in ("verify", "export"):
        sub.add_parser(name).add_argument("--acceptance-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_acceptance(args.kind)
        elif args.command == "run":
            result = accept_vertical(
                args.kind,
                _parse_json(args.source_json, "acceptance source"),
                _parse_json(args.actions_json, "acceptance actions"),
                checkpoint_at=args.checkpoint_at,
            )
        elif args.command == "import":
            result = import_acceptance(_parse_json(
                args.bundle_json, "acceptance bundle",
            ))
        else:
            report = _parse_json(args.acceptance_json, "acceptance report")
            result = (verify_acceptance(report) if args.command == "verify"
                      else export_acceptance(report))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
