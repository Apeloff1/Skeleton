"""Replay-bound NPC interaction calendar and non-authoritative player hints.

This does not predict new facts or bypass schedules. Every suggested command
is replayed through the canonical NPC session before being shown to players.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .flgb_gameplay_runtime import GameplayContractError, dig
from .npc_schedule import (
    NpcCommand, NpcSchedule, NpcSession, _integer, _keys,
)

SCHEMA = "skeleton.npc_interaction_calendar.v1"
_PLAYER_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}")
MAX_ENTRIES = 128
MAX_BYTES = 2_000_000


def _size(value: Any) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameplayContractError("invalid NPC calendar JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise GameplayContractError("NPC calendar exceeds portable size budget")


def forecast_calendar(
    schedule: NpcSchedule, session: NpcSession, *,
    player_id: str = "player", max_entries: int = 64,
) -> dict[str, Any]:
    """Show future authored encounters from the exact verified player state."""
    if not isinstance(schedule, NpcSchedule) or not isinstance(session, NpcSession):
        raise GameplayContractError("invalid NPC calendar contract")
    if session.schedule.digest != schedule.digest:
        raise GameplayContractError("NPC calendar source identity mismatch")
    if type(player_id) is not str or _PLAYER_ID.fullmatch(player_id) is None:
        raise GameplayContractError("invalid calendar player_id")
    _integer(max_entries, "max_entries", 1, MAX_ENTRIES)
    # Canonical replay protects against forged in-memory facts or event buses.
    verified = NpcSession.restore(schedule, session.snapshot())
    consumed = {
        (command.npc_id, command.interaction_id)
        for command in verified.commands if command.kind == "interact"
    }
    rows = []
    if verified.ending == "in_progress":
        for route in schedule.routes:
            for stop in route.stops:
                if stop.end_tick <= verified.tick:
                    continue
                if (route.npc_id, stop.interaction_id) in consumed:
                    continue
                next_tick = max(verified.tick, stop.start_tick)
                if next_tick > schedule.horizon_ticks:
                    continue
                missing = sorted(set(stop.requires) - set(verified.facts))
                rows.append({
                    "npc_id": route.npc_id,
                    "interaction_id": stop.interaction_id,
                    "location_id": stop.location_id,
                    "start_tick": stop.start_tick,
                    "end_tick": stop.end_tick,
                    "next_tick": next_tick,
                    "requires": list(stop.requires),
                    "grants": list(stop.grants),
                    "missing_facts": missing,
                    "availability": (
                        "missing_facts" if missing else
                        "available_now" if next_tick == verified.tick
                        else "available_later"
                    ),
                })
    rows.sort(key=lambda row: (
        row["next_tick"], row["npc_id"], row["interaction_id"],
    ))
    visible = rows[:max_entries]
    suggestion = None
    for row in visible:
        if row["missing_facts"]:
            continue
        commands = []
        if row["next_tick"] > verified.tick:
            commands.append(NpcCommand("advance", row["next_tick"]))
        commands.append(NpcCommand(
            "interact", row["next_tick"], row["npc_id"],
            row["interaction_id"], player_id,
        ))
        cursor = verified
        for command in commands:
            cursor = cursor.apply(command)
        suggestion = {
            "npc_id": row["npc_id"],
            "interaction_id": row["interaction_id"],
            "commands": [command.as_dict() for command in commands],
            "resulting_ending": cursor.ending,
            "resulting_state_digest": cursor.state_digest,
        }
        break
    record = {
        "schema_version": SCHEMA,
        "schedule_digest": schedule.digest,
        "canon_digest": schedule.canon_digest,
        "state_digest": verified.state_digest,
        "tick": verified.tick,
        "ending": verified.ending,
        "facts": list(verified.facts),
        "player_id": player_id,
        "max_entries": max_entries,
        "truncated": len(rows) > max_entries,
        "entries": visible,
        "suggestion": suggestion,
        "snapshot": verified.snapshot(),
    }
    record["checksum"] = dig(record)
    _size(record)
    return record


def verify_calendar(schedule: NpcSchedule, raw: Any) -> dict[str, Any]:
    """Reconstruct saved NPC state, all entries and any legal hint."""
    _size(raw)
    row = _keys(raw, {
        "schema_version", "schedule_digest", "canon_digest", "state_digest",
        "tick", "ending", "facts", "player_id", "max_entries",
        "truncated", "entries", "suggestion", "snapshot", "checksum",
    }, "NPC calendar")
    if row["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported NPC calendar schema")
    if row["schedule_digest"] != schedule.digest:
        raise GameplayContractError("NPC calendar schedule mismatch")
    session = NpcSession.restore(schedule, row["snapshot"])
    expected = forecast_calendar(
        schedule, session, player_id=row["player_id"],
        max_entries=row["max_entries"],
    )
    if expected != raw:
        raise GameplayContractError("NPC calendar replay or checksum mismatch")
    return expected
