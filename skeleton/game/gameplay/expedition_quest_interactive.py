"""Offline interactive NPC/crafting/combat quest over the canonical runtime.

The authored source controls topology and NPC schedules. Every move is
executed by the canonical quest engine; user input never grants inventory,
combat rewards, endings or external effects. Checkpoints replay from source.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    MAX_ACTIONS, MAX_BYTES, _action, _advance,
    export_quest, import_quest, new_quest, original_quest, verify_quest,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json,
)

MAX_INPUT_BYTES = 128 * 1024
MAX_RETRIES = 3
MAX_CHECKPOINT_INTERVAL = 64


def parse_quest_action(line: str) -> dict[str, Any]:
    if type(line) is not str:
        raise CombatSessionError("quest action must be text")
    try:
        if len(line.encode("utf-8")) > MAX_INPUT_BYTES:
            raise CombatSessionError("quest action exceeds input budget")
    except UnicodeError as exc:
        raise CombatSessionError("invalid quest action encoding") from exc
    raw = line.strip()
    if raw.startswith("{"):
        return _action(_parse_json(raw, "quest action"))
    parts = raw.split()
    if parts == ["wait"]:
        return {"kind": "wait"}
    if len(parts) == 3 and parts[0] == "talk":
        return _action({"kind": "talk", "npc_id": parts[1], "decision": parts[2]})
    if len(parts) == 2 and parts[0] in ("travel", "craft", "buy", "use", "finish"):
        verb, value = parts
        if verb in ("buy", "use"):
            return {"kind": "expedition", "action": {"kind": verb, "item_id": value}}
        key = {"travel": "to", "craft": "recipe_id", "finish": "ending_id"}[verb]
        return _action({"kind": verb, key: value})
    if parts == ["fight"]:
        return {"kind": "expedition", "action": {"kind": "fight"}}
    raise CombatSessionError(
        "use wait, travel PLACE, talk NPC aid|decline, craft RECIPE, "
        "fight, buy ITEM, use ITEM, finish ENDING or JSON"
    )


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise CombatSessionError("interactive quest output budget exceeded")
    writer.write(encoded + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    verified = verify_quest(session)
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"],
        "session": verified,
    })


def legal_quest_actions(session: Any) -> list[dict[str, Any]]:
    """Enumerate bounded visible moves; canonical _advance remains authority."""
    current = verify_quest(session)
    source, state = current["source"], current["state"]
    if state["phase"] != "active" or state["tick"] >= MAX_ACTIONS:
        return []
    candidates = [{"kind": "wait"}]
    location = next(p for p in source["locations"] if p["id"] == state["location"])
    candidates.extend({"kind": "travel", "to": dest} for dest in location["exits"])
    for npc in source["npcs"]:
        if (npc["id"] not in state["choices"]
                and npc["route"][state["tick"] % len(npc["route"])] == state["location"]):
            candidates.extend({
                "kind": "talk", "npc_id": npc["id"], "decision": decision,
            } for decision in ("aid", "decline"))
    if state["location"] == source["workshop_location"]:
        for recipe in source["recipes"]:
            if (recipe["id"] not in state["crafted"]
                    and all(state["items"].get(item, 0) > 0 for item in recipe["inputs"])):
                candidates.append({"kind": "craft", "recipe_id": recipe["id"]})
    expedition = state["expedition"]["state"]
    if state["location"] == source["camp_location"] and expedition["phase"] == "active":
        if expedition["next_index"] < len(source["expedition"]["arenas"]) and expedition["hero_hp"] > 0:
            candidates.append({"kind": "expedition", "action": {"kind": "fight"}})
        for item in source["expedition"]["shop"]:
            if (expedition["currency"] >= item["price"]
                    and expedition["purchased"].get(item["id"], 0) < item["stock"]
                    and sum(expedition["inventory"].values()) < 16):
                candidates.append({"kind": "expedition", "action": {
                    "kind": "buy", "item_id": item["id"],
                }})
            hero_max = next(a["max_hp"] for a in source["expedition"]["arenas"][0]["arena"]["actors"] if a["id"] == source["expedition"]["hero_id"])
            if (expedition["inventory"].get(item["id"], 0) > 0
                    and expedition["hero_hp"] < hero_max):
                candidates.append({"kind": "expedition", "action": {
                    "kind": "use", "item_id": item["id"],
                }})
    for ending in source["endings"]:
        if (ending["outcome"] == expedition["phase"]
                and all(state["choices"].get(c["npc_id"]) == c["decision"]
                        for c in ending["choices"])
                and all(state["items"].get(item, 0) > 0 for item in ending["items"])):
            candidates.append({"kind": "finish", "ending_id": ending["id"]})
    return sorted(candidates, key=lambda item: json.dumps(item, sort_keys=True))


def play_quest(
    source: Any = None, *, session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8, max_turns: int = 96,
    input_stream: Any = None, output_stream: Any = None,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one quest source or checkpoint")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= MAX_CHECKPOINT_INTERVAL:
        raise CombatSessionError("invalid quest checkpoint interval")
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_ACTIONS:
        raise CombatSessionError("invalid quest turn budget")
    current = new_quest(source) if session is None else verify_quest(session)
    if expected_source_digest is not None:
        if (type(expected_source_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
                or expected_source_digest != current["source_digest"]):
            raise CombatSessionError("quest trusted source digest mismatch")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    start_tick = current["state"]["tick"]
    _emit(writer, {"event": "started", "source_digest": current["source_digest"],
                   "state_digest": current["state_digest"], "tick": start_tick})
    while current["state"]["phase"] == "active":
        if current["state"]["tick"] - start_tick >= max_turns:
            _checkpoint(writer, current, "turn_budget")
            raise CombatSessionError("quest turn budget exhausted; checkpoint emitted")
        state = current["state"]
        available = legal_quest_actions(current)
        _emit(writer, {
            "event": "prompt", "tick": state["tick"], "location": state["location"],
            "items": state["items"], "crafted": state["crafted"],
            "choices": state["choices"], "expedition": {
                "phase": state["expedition"]["state"]["phase"],
                "hero_hp": state["expedition"]["state"]["hero_hp"],
                "currency": state["expedition"]["state"]["currency"],
                "inventory": state["expedition"]["state"]["inventory"],
            }, "available_actions": available,
            "manual_tactical_note": "JSON expedition fight_tactical actions are validated by canonical combat",
            "state_digest": current["state_digest"],
        })
        if not available:
            _checkpoint(writer, current, "no_legal_action")
            raise CombatSessionError("no legal quest action; checkpoint emitted")
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_INPUT_BYTES + 1)
            if not line:
                _checkpoint(writer, current, "input_eof")
                raise CombatSessionError("quest input ended; checkpoint emitted")
            try:
                action = parse_quest_action(line)
                manual = (action.get("kind") == "expedition"
                          and action.get("action", {}).get("kind") == "fight_tactical")
                if action not in available and not manual:
                    raise CombatSessionError("quest action unavailable in current state")
                updated = _advance(current, action)
            except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
                _emit(writer, {"event": "invalid", "attempt": attempt + 1,
                               "error": str(exc)})
                if attempt + 1 == MAX_RETRIES:
                    _checkpoint(writer, current, "invalid_input_limit")
                    raise CombatSessionError("quest retries exhausted; checkpoint emitted") from exc
                continue
            current = updated
            _emit(writer, {"event": "accepted", "tick": current["state"]["tick"],
                           "state_digest": current["state_digest"],
                           "action_receipt": current["journal"][-1]["receipt"]})
            if current["state"]["tick"] % checkpoint_every == 0:
                _checkpoint(writer, current, "interval")
            break
    current = verify_quest(current)
    bundle = export_quest(current)
    if import_quest(bundle) != current:
        raise CombatSessionError("quest terminal portable roundtrip mismatch")
    _checkpoint(writer, current, "terminal")
    _emit(writer, {"event": "terminal", "ending": current["state"]["ending"],
                   "state_digest": current["state_digest"], "bundle": bundle})
    return current


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-expedition-play")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--resume-json")
    parser.add_argument("--source-digest")
    parser.add_argument("--checkpoint-every", type=int, default=8)
    parser.add_argument("--max-turns", type=int, default=96)
    args = parser.parse_args(list(argv))
    try:
        saved = (_parse_json(args.resume_json, "quest save")
                 if args.resume_json is not None else None)
        source = (original_quest() if args.demo else
                  _parse_json(args.source_json, "quest source")
                  if args.source_json is not None else None)
        play_quest(
            source, session=saved, expected_source_digest=args.source_digest,
            checkpoint_every=args.checkpoint_every, max_turns=args.max_turns,
        )
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
