"""Local playable terminal for the original-world campaign pilot.

This is an offline abstract turn-based game. Text visuals, JSON scripts and
savegames use only the Python standard library and never require proprietary
game-console software, AI providers, or network access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_world_campaign import (
    ACTION_MECHANICS, ROOM_COUNT, SCENARIOS, CampaignAction, CampaignError,
    CampaignState, create_campaign, edges, export_save, import_save,
    neighbors, step,
)

MAX_SCRIPT_BYTES = 65536


def render(state: CampaignState) -> str:
    """A compact playable map without conflating unseen sectors with empty ones."""
    visited = set(state.explored)
    rows = []
    for y in range(3):
        cells = []
        for x in range(4):
            i = y * 4 + x
            marker = "@" if i == state.position else ("." if i in visited else "?")
            cells.append(f"{marker}{i:02d}")
        rows.append("  ".join(cells))
    current = state.sectors[state.position]
    return "\n".join([
        *rows,
        f"World: {state.world_id} | Turn: {state.turn} | AP: {state.action_points}",
        f"Place: {current.name} ({current.biome}), exits: {', '.join(map(str, neighbors(state)))}",
        f"Energy {state.energy}/20 | Health {state.health}/20 | Hunger {state.hunger}/20",
        f"Food {state.food} | Water {state.water} | Wood {state.wood} | Stone {state.stone}",
        f"Seeds {state.seeds} | Tools {state.tools} | Coins {state.coins} | Medicine {state.medicine}",
        f"Trust {state.trust} | Knowledge {state.knowledge} | Quilt {state.quilt}",
        f"Progress {state.quest_progress}/100 | "
        + ("Postgame: ongoing" if state.postgame else "Chapter: unfolding"),
    ])


def _decode_action(value: dict) -> CampaignAction:
    if not isinstance(value, dict) or set(value) - {"verb", "target", "amount", "option"}:
        raise CampaignError("unexpected action fields")
    try:
        action = CampaignAction(**value)
    except (TypeError, ValueError) as exc:
        raise CampaignError("invalid action format") from exc
    if action.verb not in ACTION_MECHANICS:
        raise CampaignError("unknown action")
    return action


def parse_script(serialized: str) -> tuple[CampaignAction, ...]:
    if not isinstance(serialized, str) or len(serialized.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise CampaignError("oversized or invalid action script")
    try:
        raw = json.loads(serialized)
    except (ValueError, TypeError) as exc:
        raise CampaignError("invalid JSON actions") from exc
    if not isinstance(raw, list) or len(raw) > 1024:
        raise CampaignError("action script must be bounded list")
    return tuple(_decode_action(x) for x in raw)


def _parse_terminal(line: str) -> CampaignAction:
    try:
        words = shlex.split(line)
    except ValueError as exc:
        raise CampaignError("invalid terminal command syntax") from exc
    if not words:
        raise CampaignError("empty command")
    verb = words[0].replace("-", "_")
    if verb not in ACTION_MECHANICS:
        raise CampaignError("unknown command")
    if len(words) > 3:
        raise CampaignError("expected: VERB [TARGET/OPTION/AMOUNT] [AMOUNT]")
    if verb in {"move", "stabilize_route"}:
        if len(words) not in (2, 3):
            raise CampaignError("movement commands require a numeric target")
        try:
            return CampaignAction(verb, int(words[1]), int(words[2]) if len(words) == 3 else 1)
        except ValueError as exc:
            raise CampaignError("invalid movement number") from exc
    if verb in {"trade", "redirect_rain"}:
        if len(words) not in (2, 3):
            raise CampaignError("command requires an option")
        try:
            return CampaignAction(verb, -1, int(words[2]) if len(words) == 3 else 1, words[1])
        except ValueError as exc:
            raise CampaignError("invalid quantity") from exc
    if len(words) not in (1, 2):
        raise CampaignError("command takes one optional quantity")
    try:
        return CampaignAction(verb, -1, int(words[1]) if len(words) == 2 else 1)
    except ValueError as exc:
        raise CampaignError("invalid quantity") from exc


def _save(path: Path, state: CampaignState) -> None:
    if path.exists() and path.is_dir():
        raise CampaignError("save destination is a directory")
    if not path.parent.is_dir():
        raise CampaignError("save parent directory does not exist")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(export_save(state), encoding="utf-8")
    temporary.replace(path)


def _load(path: Path) -> CampaignState:
    if not path.is_file() or path.stat().st_size > 262144:
        raise CampaignError("invalid or oversized save file")
    return import_save(path.read_text(encoding="utf-8"))


def _interactive(state: CampaignState, save_path: Path | None) -> CampaignState:
    print("Original Worlds — offline pilot. Commands: map, status, help, save, quit.")
    print(render(state))
    while True:
        try:
            line = input("world> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nClosed local terminal.")
            break
        if not line:
            continue
        if line in {"quit", "exit"}:
            break
        if line in {"status", "map"}:
            print(render(state))
            continue
        if line == "help":
            print("Commands:", ", ".join(sorted(ACTION_MECHANICS)))
            print("move N | trade buy_food N | redirect_rain west N | end_turn")
            continue
        if line == "save":
            if save_path is None:
                print("No --save path configured.")
            else:
                try:
                    _save(save_path, state)
                    print("Saved to", save_path)
                except (CampaignError, OSError) as exc:
                    print("Save rejected:", exc)
            continue
        try:
            state, receipt = step(state, _parse_terminal(line))
            print(" | ".join(receipt.messages))
            print(render(state))
        except (CampaignError, OSError) as exc:
            print("Action rejected:", exc)
    if save_path is not None:
        _save(save_path, state)
        print("Saved to", save_path)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play four authored world-law scenarios offline.")
    parser.add_argument("--world", choices=sorted(SCENARIOS), default="serenity-05")
    parser.add_argument("--seed", default="original-world-play")
    parser.add_argument("--actions-json", help="Bounded sequence of gameplay actions")
    parser.add_argument("--load", type=Path, help="Resume a previously exported save")
    parser.add_argument("--save", type=Path, help="Save completed or interactive state")
    parser.add_argument("--interactive", action="store_true", help="Run playable terminal")
    parser.add_argument("--show-map", action="store_true", help="Print text map instead of JSON")
    args = parser.parse_args(argv)
    try:
        state = _load(args.load) if args.load else create_campaign(args.world, args.seed)
        if args.actions_json is not None:
            for action in parse_script(args.actions_json):
                state, _ = step(state, action)
        if args.interactive:
            _interactive(state, args.save)
        else:
            if args.save:
                _save(args.save, state)
            if args.show_map:
                print(render(state))
            else:
                print(json.dumps({
                    "status": "playable-abstract-4-worlds",
                    "state": json.loads(export_save(state))["payload"]["state"],
                    "available_actions": sorted(ACTION_MECHANICS),
                    "note": "Four authored world adapters, not the complete game library.",
                }, sort_keys=True, indent=2))
    except (CampaignError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
