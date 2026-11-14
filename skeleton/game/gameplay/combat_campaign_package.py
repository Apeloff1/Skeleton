"""Portable, replay-verified offline combat campaign checkpoints.

The bundle is deterministic JSON, not an authenticity signature or a file
system permission. It never reads arbitrary paths or executes authored code.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign import (
    advance_campaign, finish_campaign, new_campaign, normalize_campaign,
    original_campaign, verify_campaign,
)
from skeleton.game.gameplay.combat_campaign_author import _bounded_json
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_package.v1"


def _manifest(source: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    state = snapshot["state"]
    return {
        "world_id": source["world_id"],
        "campaign_id": source["campaign_id"],
        "hero_id": source["hero_id"],
        "phase": state["phase"],
        "next_index": state["next_index"],
        "hero_hp": state["hero_hp"],
        "currency": state["currency"],
        "encounters": [
            {
                "encounter_id": encounter["encounter_id"],
                "reward": encounter["reward"],
                "combat_state_digest": encounter["combat"]["state_digest"],
                "combat_save_digest": dig(encounter["combat"]["save"]),
            }
            for encounter in state["encounters"]
        ],
        "campaign_save_digest": dig(snapshot["save"]),
    }


def package_campaign(source: Any, session: Any) -> dict[str, Any]:
    """Export a checkpoint only after independently replaying its full journal."""
    spec = normalize_campaign(source)
    verified = verify_campaign(session)
    if verified["source_digest"] != dig(spec):
        raise CombatSessionError("portable campaign source mismatch")
    manifest = _manifest(spec, verified)
    result = {
        "schema_version": SCHEMA,
        "source": spec,
        "source_digest": dig(spec),
        "snapshot": verified,
        "snapshot_digest": dig(verified),
        "manifest": manifest,
        "claim": "integrity_checked_offline_save",
    }
    result["receipt"] = dig(result)
    _bounded_json(result)
    return result


def verify_package(raw: Any) -> dict[str, Any]:
    """Reject edited source, reward, journal, manifest, and save lineage."""
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "snapshot",
        "snapshot_digest", "manifest", "claim", "receipt",
    }, "portable campaign")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "integrity_checked_offline_save":
        raise CombatSessionError("unsupported portable campaign schema")
    _bounded_json(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("portable campaign receipt mismatch")
    expected = package_campaign(obj["source"], obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("portable campaign manifest or replay mismatch")
    return expected


def resume_package(raw: Any) -> dict[str, Any]:
    """Finish only verified incomplete checkpoints; terminal import is idempotent."""
    saved = verify_package(raw)
    source, session = saved["source"], saved["snapshot"]
    if session["state"]["phase"] != "active":
        return saved
    completed = finish_campaign(source, resume=session)
    return package_campaign(source, completed)


def original_package_demo() -> dict[str, Any]:
    source = original_campaign()
    first_checkpoint = advance_campaign(new_campaign(source))
    return package_campaign(source, first_checkpoint)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Export original patrol's first verified checkpoint")
    pack = sub.add_parser("pack", help="Package source and canonical save for offline use")
    pack.add_argument("--source-json", required=True)
    pack.add_argument("--session-json", required=True)
    for command in ("verify", "resume"):
        item = sub.add_parser(command)
        item.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_package_demo()
        elif args.command == "pack":
            result = package_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.session_json, "campaign session"),
            )
        else:
            raw = _parse_json(args.package_json, "portable campaign")
            result = verify_package(raw) if args.command == "verify" else resume_package(raw)
        print(_bounded_json(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
