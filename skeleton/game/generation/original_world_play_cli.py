"""Unified offline play interface: world, autonomous settlement and multiverse.

Interactive, scriptable and saveable without provider AI, external assets or
unlicensed platform SDKs. All inputs are explicit bounded operations. Save
checksums catch accidental corruption; they are not signatures/authentication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_world_campaign import (
    ACTION_MECHANICS, SCENARIOS, CampaignAction, CampaignError,
    CampaignState, create_campaign, export_save, import_save, step,
)
from .original_world_campaign_cli import render as world_map
from .original_world_campaign_cli import _parse_terminal as parse_world_command
from .original_world_living_session import (
    create_living_session, living_restore, living_save, living_step,
)
from .original_world_nexus import (
    REALM_IDS, NexusState, act as nexus_act, active_world,
    connections, create_nexus, nexus_restore, nexus_save,
    recharge as nexus_recharge, travel as nexus_travel,
)
from .original_world_society import LivingSession, SocietyAction

MODES = ("campaign", "living", "nexus")
MAX_SCRIPT = 65536


def _render(state: CampaignState | LivingSession | NexusState) -> str:
    if isinstance(state, CampaignState):
        return world_map(state)
    if isinstance(state, LivingSession):
        residents = state.society.residents
        nearby = [r for r in residents if r.location == state.campaign.position]
        display = [world_map(state.campaign), "Living society:"]
        display.append(
            "Local residents: " + (
                ", ".join(f"{r.id}:{r.name}({r.profession},trust={r.trust})"
                          for r in nearby) or "none"))
        for village in state.society.villages:
            display.append(
                f"Village {village.location}: food={village.food} "
                f"water={village.water} wood={village.timber} "
                f"funds={village.funds} welfare={village.welfare} "
                f"projects={village.projects}")
        display.append(f"Council {state.society.council}, "
                       f"shared knowledge {state.society.common_knowledge}")
        return "\n".join(display)
    active = active_world(state)
    display = [world_map(active),
               f"World nexus: {state.current_realm} "
               f"({REALM_IDS[state.current_realm]})",
               "Connected worlds: " + ", ".join(map(str, connections(state))),
               f"Travel charges: {state.charges}",
               f"Chapters completed in worlds: {list(state.completed_realms)}"]
    for index, realm in enumerate(state.realms):
        display.append(
            f"Realm {index} {realm.world_id}: turn {realm.turn}, "
            f"explored {len(realm.explored)}, "
            f"chapter {'complete' if realm.chapter_complete else 'open'}")
    return "\n".join(display)


def _parse_script(raw: str, mode: str) -> tuple[tuple[str, object], ...]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_SCRIPT:
        raise CampaignError("invalid or oversized play script")
    try:
        items = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise CampaignError("invalid JSON play script") from exc
    if not isinstance(items, list) or len(items) > 1024:
        raise CampaignError("play script must be a bounded JSON array")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise CampaignError("each command must be a structured object")
        if "verb" in item:
            if set(item) - {"verb", "target", "amount", "option"}:
                raise CampaignError("unknown world-action fields")
            action = CampaignAction(**item)
            if action.verb not in ACTION_MECHANICS:
                raise CampaignError("unsupported gameplay action")
            result.append(("world", action))
        elif "social" in item and mode == "living":
            if set(item) - {"social", "resident", "amount"}:
                raise CampaignError("unknown social-action fields")
            result.append(("social", SocietyAction(
                item["social"], item.get("resident", 0),
                item.get("amount", 1))))
        elif "portal" in item and mode == "nexus":
            if set(item) != {"portal"}:
                raise CampaignError("portal commands have one target only")
            result.append(("portal", item["portal"]))
        elif "recharge" in item and mode == "nexus":
            if set(item) != {"recharge"}:
                raise CampaignError("recharge commands have one amount only")
            result.append(("recharge", item["recharge"]))
        else:
            raise CampaignError("unknown or inapplicable game command")
    return tuple(result)


def _apply(state, operation: tuple[str, object]):
    kind, payload = operation
    if isinstance(state, CampaignState):
        if kind != "world" or not isinstance(payload, CampaignAction):
            raise CampaignError("solo mode accepts only world actions")
        new, receipt = step(state, payload)
        return new, receipt.messages
    if isinstance(state, LivingSession):
        if kind not in {"world", "social"}:
            raise CampaignError("living mode accepts world and social actions")
        new, receipt = living_step(state, payload)
        return new, receipt.messages
    if kind == "world":
        new, receipt = nexus_act(state, payload)
    elif kind == "portal":
        new, receipt = nexus_travel(state, payload)
    elif kind == "recharge":
        new, receipt = nexus_recharge(state, payload)
    else:
        raise CampaignError("unsupported nexus command")
    return new, receipt.messages


def _encode(state) -> str:
    if isinstance(state, CampaignState):
        return export_save(state)
    if isinstance(state, LivingSession):
        return living_save(state)
    if isinstance(state, NexusState):
        return nexus_save(state)
    raise CampaignError("unrecognized save mode")


def _decode(serialized: str, mode: str):
    if mode == "campaign":
        return import_save(serialized)
    if mode == "living":
        return living_restore(serialized)
    return nexus_restore(serialized)


def _save(path: Path, state) -> None:
    if not path.parent.is_dir() or path.is_dir():
        raise CampaignError("invalid save destination")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(_encode(state), encoding="utf-8")
    temporary.replace(path)


def _load(path: Path, mode: str):
    if not path.is_file() or path.stat().st_size > 1048576:
        raise CampaignError("invalid or oversized save")
    return _decode(path.read_text(encoding="utf-8"), mode)


def _parse_terminal(line: str, mode: str) -> tuple[str, object]:
    try:
        words = shlex.split(line)
    except ValueError as exc:
        raise CampaignError("unclosed quotation in command") from exc
    if not words:
        raise CampaignError("empty command")
    if words[0] == "portal" and mode == "nexus" and len(words) == 2:
        try:
            return ("portal", int(words[1]))
        except ValueError as exc:
            raise CampaignError("portal target must be an integer") from exc
    if words[0] == "recharge" and mode == "nexus":
        if len(words) not in (1, 2):
            raise CampaignError("recharge accepts one optional quantity")
        try:
            return ("recharge", int(words[1]) if len(words) == 2 else 1)
        except ValueError as exc:
            raise CampaignError("invalid recharge quantity") from exc
    if words[0] == "social" and mode == "living":
        if not 2 <= len(words) <= 4:
            raise CampaignError("use social VERB [RESIDENT] [QUANTITY]")
        try:
            return ("social", SocietyAction(
                words[1], int(words[2]) if len(words) >= 3 else 0,
                int(words[3]) if len(words) == 4 else 1))
        except ValueError as exc:
            raise CampaignError("invalid social command integer") from exc
    return "world", parse_world_command(line)


def _interactive(state, mode: str, save_path: Path | None):
    print("Original Worlds Play —", mode, "mode.")
    print("Commands: map, status, help, save, quit; world actions use the verb.")
    print(_render(state))
    while True:
        try:
            line = input("play> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped local play.")
            break
        if not line:
            continue
        if line in {"quit", "exit"}:
            break
        if line in {"map", "status"}:
            print(_render(state))
            continue
        if line == "help":
            print("World verbs:", ", ".join(sorted(ACTION_MECHANICS)))
            if mode == "living":
                print("NPC commands: social greet 0; social invite 0; "
                      "social trade_food 0 2; social petition 0")
            if mode == "nexus":
                print("Cross-world commands: portal 1; recharge 1")
            continue
        if line == "save":
            if save_path is None:
                print("Supply --save to enable saving.")
            else:
                _save(save_path, state)
                print("State saved.")
            continue
        try:
            state, result = _apply(state, _parse_terminal(line, mode))
            print(" | ".join(result))
            print(_render(state))
        except (CampaignError, OSError) as exc:
            print("Action refused:", exc)
    if save_path:
        _save(save_path, state)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play original worlds offline with NPCs and interconnected realms."
    )
    parser.add_argument("--mode", choices=MODES, default="campaign")
    parser.add_argument("--world", choices=sorted(SCENARIOS), default="serenity-05")
    parser.add_argument("--seed", default="original-world-journey")
    parser.add_argument("--actions-json")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--save", type=Path)
    parser.add_argument("--load", type=Path)
    parser.add_argument("--show-map", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.load:
            state = _load(args.load, args.mode)
        elif args.mode == "living":
            state = create_living_session(args.world, args.seed)
        elif args.mode == "nexus":
            state = create_nexus(args.seed)
        else:
            state = create_campaign(args.world, args.seed)
        for command in _parse_script(args.actions_json or "[]", args.mode):
            state, _ = _apply(state, command)
        if args.interactive:
            _interactive(state, args.mode, args.save)
        else:
            if args.save:
                _save(args.save, state)
            if args.show_map:
                print(_render(state))
            else:
                print(json.dumps({
                    "mode": args.mode,
                    "status": "playable-abstract",
                    "state": json.loads(_encode(state))["payload"],
                    "render": _render(state),
                    "available_world_actions": sorted(ACTION_MECHANICS),
                }, sort_keys=True, ensure_ascii=False, indent=2))
    except (CampaignError, OSError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
