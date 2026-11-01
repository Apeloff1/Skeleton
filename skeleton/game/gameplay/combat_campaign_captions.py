"""Replay-verified accessible combat captions for original offline campaigns.

Captions are a deterministic *view* of canonical turns, not an alternate game
engine. No text is executed, no rewards are granted, and integrity digests are
not signatures or author authorization. Both partial and terminal checkpoints
are supported for accessible play and portable offline transcripts.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import (
    advance_campaign, finish_campaign, new_campaign, original_campaign,
    verify_campaign,
)
from skeleton.game.gameplay.combat_inspector import inspect_session
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_captions.v1"
PAGE_SCHEMA = "skeleton.combat_campaign_caption_page.v1"
MAX_PAGE_SIZE = 64
MAX_EVENTS = 128


def _json(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CombatSessionError("invalid combat captions JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError("combat captions exceed 128 KiB")
    return encoded


def _caption(action: dict[str, str], changes: dict[str, Any],
             phase: str, winner: str | None) -> tuple[str, int, int, bool]:
    """Derive human-readable effects only from replayed before/after HP."""
    actor = action["actor_id"]
    kind = action["kind"]
    damage = 0
    healing = 0
    knockout = False
    if kind == "attack":
        target = action["target_id"]
        change = changes.get(target)
        if change is None:
            raise CombatSessionError("replayed attack missing target transition")
        damage = change["hp_before"] - change["hp_after"]
        if damage <= 0:
            raise CombatSessionError("replayed attack did not damage target")
        knockout = change["hp_before"] > 0 and change["hp_after"] == 0
        message = f"{actor} strikes {target} for {damage} damage."
        if knockout:
            message += f" {target} falls."
    elif kind == "guard":
        message = f"{actor} braces for the next attack."
    elif kind == "rest":
        change = changes.get(actor)
        if change is not None:
            healing = change["hp_after"] - change["hp_before"]
        if healing < 0:
            raise CombatSessionError("replayed rest reduced health")
        message = f"{actor} rests and recovers {healing} health."
    else:
        raise CombatSessionError("unknown replayed combat action")
    if phase == "won":
        message += f" {winner} wins the encounter."
    elif phase == "draw":
        message += " The encounter ends in a draw."
    return message, damage, healing, knockout


def build_captions(raw: Any) -> dict[str, Any]:
    """Replay every campaign encounter and render an accessible turn journal."""
    session = verify_campaign(raw)
    source = session["source"]
    state = session["state"]
    captions: list[dict[str, Any]] = []
    encounters: list[dict[str, Any]] = []
    total_damage = 0
    total_healing = 0
    total_knockouts = 0
    earned_currency = 0
    for encounter_index, entry in enumerate(state["encounters"]):
        combat = entry["combat"]
        inspection = inspect_session(combat)
        scenario = combat["scenario"]
        actors = {actor["id"]: actor for actor in scenario["actors"]}
        encounter_damage = 0
        encounter_healing = 0
        for turn in inspection["timeline"]:
            action = turn["action"]
            if action["actor_id"] not in actors:
                raise CombatSessionError("unknown actor in replay")
            message, damage, healing, knockout = _caption(
                action, turn["changes"], turn["phase"], turn["winner"],
            )
            encounter_damage += damage
            encounter_healing += healing
            total_damage += damage
            total_healing += healing
            total_knockouts += int(knockout)
            row = {
                "sequence": len(captions),
                "encounter_index": encounter_index,
                "encounter_id": entry["encounter_id"],
                "turn": turn["turn"],
                "actor_id": action["actor_id"],
                "target_id": action.get("target_id"),
                "action": action["kind"],
                "damage": damage,
                "healing": healing,
                "knockout": knockout,
                "caption": message,
                "after_digest": turn["after_digest"],
                "turn_receipt": turn["receipt"],
            }
            captions.append(row)
            if len(captions) > MAX_EVENTS:
                raise CombatSessionError("combat caption turn budget exceeded")
        earned_currency += entry["reward"]
        encounters.append({
            "encounter_index": encounter_index,
            "encounter_id": entry["encounter_id"],
            "first_caption": len(captions) - len(inspection["timeline"]),
            "caption_count": len(inspection["timeline"]),
            "phase": inspection["phase"],
            "winner": inspection["winner"],
            "reward": entry["reward"],
            "currency_after": earned_currency,
            "damage": encounter_damage,
            "healing": encounter_healing,
            "combat_state_digest": inspection["state_digest"],
        })
    if earned_currency != state["currency"]:
        raise CombatSessionError("campaign currency and replay rewards diverged")
    manifest = {
        "world_id": source["world_id"],
        "campaign_id": source["campaign_id"],
        "hero_id": source["hero_id"],
        "phase": state["phase"],
        "completed_encounters": len(encounters),
        "caption_count": len(captions),
        "total_damage": total_damage,
        "total_healing": total_healing,
        "total_knockouts": total_knockouts,
        "earned_currency": earned_currency,
        "source_digest": session["source_digest"],
        "session_digest": dig(session),
        "captions_digest": dig(captions),
    }
    result = {
        "schema_version": SCHEMA,
        "session": session,
        "manifest": manifest,
        "encounters": encounters,
        "captions": captions,
        "integrity_claim": "replay_checked_not_authenticated",
    }
    result["receipt"] = dig(result)
    _json(result)
    return result


def verify_captions(raw: Any) -> dict[str, Any]:
    """Reject any altered narration, turns, outcome, save, or source."""
    obj = _object(raw, {
        "schema_version", "session", "manifest", "encounters",
        "captions", "integrity_claim", "receipt",
    }, "combat captions")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported combat captions schema")
    if obj["integrity_claim"] != "replay_checked_not_authenticated":
        raise CombatSessionError("unsupported combat captions integrity claim")
    _json(obj)
    if obj["receipt"] != dig({key: value for key, value in obj.items()
                              if key != "receipt"}):
        raise CombatSessionError("combat captions receipt mismatch")
    rebuilt = build_captions(obj["session"])
    if rebuilt != obj:
        raise CombatSessionError("combat captions replay mismatch")
    return rebuilt


def caption_page(raw: Any, *, offset: int = 0,
                 limit: int = 24) -> dict[str, Any]:
    """Bounded accessible reading without losing full replay provenance."""
    transcript = verify_captions(raw)
    offset = _integer(offset, "offset", 0, MAX_EVENTS)
    limit = _integer(limit, "limit", 1, MAX_PAGE_SIZE)
    rows = transcript["captions"]
    if offset > len(rows):
        raise CombatSessionError("caption page offset exceeds journal")
    selected = rows[offset:offset + limit]
    result = {
        "schema_version": PAGE_SCHEMA,
        "manifest": transcript["manifest"],
        "transcript_receipt": transcript["receipt"],
        "offset": offset,
        "limit": limit,
        "next_offset": offset + len(selected) if offset + len(selected) < len(rows) else None,
        "captions": selected,
    }
    result["receipt"] = dig(result)
    _json(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton combat-campaign-captions",
        description="Replay-verified, screen-reader-friendly offline combat narration",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Caption the complete original patrol")
    build = commands.add_parser("build", help="Caption a verified campaign checkpoint")
    build.add_argument("--session-json", required=True)
    verify = commands.add_parser("verify", help="Replay-verify a portable transcript")
    verify.add_argument("--transcript-json", required=True)
    page = commands.add_parser("page", help="Read a bounded caption page")
    page.add_argument("--transcript-json", required=True)
    page.add_argument("--offset", type=int, default=0)
    page.add_argument("--limit", type=int, default=24)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = build_captions(finish_campaign(original_campaign()))
        elif args.command == "build":
            result = build_captions(_parse_json(args.session_json, "campaign checkpoint"))
        elif args.command == "verify":
            result = verify_captions(_parse_json(args.transcript_json, "captions"))
        else:
            result = caption_page(
                _parse_json(args.transcript_json, "captions"),
                offset=args.offset, limit=args.limit,
            )
        print(_json(result))
        return 0
    except (CombatSessionError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
