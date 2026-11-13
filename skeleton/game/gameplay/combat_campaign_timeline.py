"""Canonical player campaign replay timeline and earned-reward accounting.

A read-only debugger for player decisions, opponent responses, carried health,
and currency. It never invents combat actions or grants rewards independently
of the verified campaign reducer. Offline receipts are not signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_player import (
    _advance, _bounded, demo_player_campaign, export_player_campaign,
    import_player_campaign, new_player_campaign, resume_player_campaign,
    verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_timeline.v1"
BUNDLE = "skeleton.combat_campaign_timeline_bundle.v1"
MAX_EVENTS = 512


def audit_player_campaign(payload: Any) -> dict[str, Any]:
    """Recompute every checkpoint and currency delta from original source."""
    canonical = verify_player_campaign(payload)
    source = canonical["source"]
    replay = new_player_campaign(source)
    entries: list[dict[str, Any]] = []
    if len(canonical["journal"]) > MAX_EVENTS:
        raise CombatSessionError("campaign timeline event budget exceeded")
    for sequence, event in enumerate(canonical["journal"]):
        before = replay["state"]
        before_completed = len(before["completed"])
        before_currency = before["currency"]
        before_hp = before["hero_hp"]
        replay = _advance(replay, event["action"])
        after = replay["state"]
        if replay["journal"][-1] != event:
            raise CombatSessionError("campaign timeline event receipt mismatch")
        earned = after["currency"] - before_currency
        newly_completed = after["completed"][before_completed:]
        witnessed = sum(item["reward"] for item in newly_completed)
        if earned != witnessed or earned < 0:
            raise CombatSessionError("campaign reward provenance mismatch")
        entries.append({
            "sequence": sequence,
            "action": event["action"],
            "action_receipt": event["receipt"],
            "combat_receipt": event["combat_receipt"],
            "before_state_digest": event["before"],
            "after_state_digest": replay["state_digest"],
            "combat_state_digest": after["combat"]["state_digest"],
            "hero_hp_before": before_hp,
            "hero_hp_after": after["hero_hp"],
            "hero_hp_delta": after["hero_hp"] - before_hp,
            "earned_currency": earned,
            "currency_after": after["currency"],
            "completed_encounters": [
                item["encounter_id"] for item in newly_completed
            ],
            "encounter_index_after": after["next_index"],
            "phase_after": after["phase"],
        })
    if replay != canonical:
        raise CombatSessionError("campaign timeline final replay mismatch")
    earned_total = sum(item["earned_currency"] for item in entries)
    completed_rewards = sum(
        item["reward"] for item in canonical["state"]["completed"]
    )
    if earned_total != canonical["state"]["currency"] or earned_total != completed_rewards:
        raise CombatSessionError("campaign currency conservation mismatch")
    report = {
        "schema_version": SCHEMA,
        "source_digest": canonical["source_digest"],
        "state_digest": canonical["state_digest"],
        "event_count": len(entries),
        "starting_state_digest": new_player_campaign(source)["state_digest"],
        "last_event_receipt": entries[-1]["action_receipt"] if entries else None,
        "hero_id": source["hero_id"],
        "hero_hp": canonical["state"]["hero_hp"],
        "earned_currency": earned_total,
        "completed_encounters": [
            item["encounter_id"] for item in canonical["state"]["completed"]
        ],
        "phase": canonical["state"]["phase"],
        "entries": entries,
        "qualification": "offline_replay_provenance_only",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_player_timeline(session: Any, report: Any) -> dict[str, Any]:
    """Reject a rewritten timeline even if its checksum is recomputed."""
    _bounded(report)
    expected = audit_player_campaign(session)
    if type(report) is not dict or report != expected:
        raise CombatSessionError("campaign timeline witness mismatch")
    return expected


def export_player_timeline(session: Any) -> dict[str, Any]:
    canonical = verify_player_campaign(session)
    report = audit_player_campaign(canonical)
    bundle = {
        "schema_version": BUNDLE,
        "source_digest": canonical["source_digest"],
        "state_digest": canonical["state_digest"],
        "game": export_player_campaign(canonical),
        "timeline": report,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_player_timeline(bundle: Any) -> dict[str, Any]:
    _bounded(bundle)
    obj = _object(bundle, {
        "schema_version", "source_digest", "state_digest",
        "game", "timeline", "checksum",
    }, "campaign timeline bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported campaign timeline bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items()
                               if k != "checksum"}):
        raise CombatSessionError("campaign timeline bundle checksum mismatch")
    session = import_player_campaign(obj["game"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise CombatSessionError("campaign timeline bundle source mismatch")
    verify_player_timeline(session, obj["timeline"])
    return session


def resume_player_timeline(bundle: Any, actions: Any) -> dict[str, Any]:
    """Continue a portable save through the canonical player reducer."""
    session = import_player_timeline(bundle)
    if type(actions) is not list or len(actions) > 128:
        raise CombatSessionError("invalid campaign timeline action batch")
    resumed = resume_player_campaign(session, actions)
    return export_player_timeline(resumed)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-timeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name in ("audit", "export"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--bundle-json", required=True)
    resume.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = export_player_timeline(demo_player_campaign())
        elif args.command == "audit":
            result = audit_player_campaign(
                _parse_json(args.session_json, "campaign save"),
            )
        elif args.command == "verify":
            result = verify_player_timeline(
                _parse_json(args.session_json, "campaign save"),
                _parse_json(args.report_json, "campaign timeline"),
            )
        elif args.command == "export":
            result = export_player_timeline(
                _parse_json(args.session_json, "campaign save"),
            )
        elif args.command == "import":
            result = import_player_timeline(
                _parse_json(args.bundle_json, "campaign timeline bundle"),
            )
        else:
            result = resume_player_timeline(
                _parse_json(args.bundle_json, "campaign timeline bundle"),
                _parse_json(args.actions_json, "campaign actions"),
            )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
