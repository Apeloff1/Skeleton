"""One-player product entry point: original world + living rules + 2D landscape.

Offline game with deterministic actor turns, construction, physical movement,
scripted or human controls, source-derived SVG and native PPM render output,
persisted saves and an optional real Tk desktop window.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_foundation_compiler import FoundationError
from .original_world_living_10x_compiler import (
    living_at, living_for, living_inventory,
)
from .original_world_product_session import (
    ProductAction, ProductSession, create_product, product_restore,
    product_save, step_product, validate_product,
)
from .original_world_product_render import (
    ascii_render, ppm_render, svg_render,
)
from .original_world_product_missions import mission_report

MAX_SCRIPT = 131072


def parse_script(text: str) -> tuple[ProductAction, ...]:
    if not isinstance(text, str) or len(text.encode()) > MAX_SCRIPT:
        raise FoundationError("product action script too long")
    try:
        entries = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise FoundationError("invalid game script") from exc
    if not isinstance(entries, list) or len(entries) > 2048:
        raise FoundationError("product script requires a bounded action list")
    output = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {
            "layer", "verb", "amount", "x", "y", "target", "option",
        }:
            raise FoundationError("unrecognized product action fields")
        try:
            output.append(ProductAction(**entry))
        except (TypeError, ValueError) as exc:
            raise FoundationError("malformed product command") from exc
    return tuple(output)


def parse_command(command: str, player: tuple[int, int]) -> ProductAction:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise FoundationError("invalid input quotation") from exc
    if not 2 <= len(parts) <= 4:
        raise FoundationError("expected LAYER VERB [AMOUNT|TARGET|CHOICE]")
    layer, verb = parts[:2]
    if layer == "terrain":
        if verb in ("walk", "jump", "bridge", "dig"):
            direction = parts[2] if len(parts) >= 3 else ""
            offsets = {"north": (0, -1), "south": (0, 1),
                       "east": (1, 0), "west": (-1, 0)}
            if direction not in offsets:
                raise FoundationError("terrain movement requires north, south, east or west")
            dx, dy = offsets[direction]
            return ProductAction(layer, verb, x=player[0] + dx, y=player[1] + dy)
        if len(parts) > 3:
            raise FoundationError("terrain action takes one quantity")
        try:
            count = int(parts[2]) if len(parts) == 3 else 1
        except ValueError as exc:
            raise FoundationError("invalid terrain amount") from exc
        return ProductAction(layer, verb, amount=count, x=player[0], y=player[1])
    if verb == "choose" or (layer == "studio" and verb == "assign"):
        if len(parts) not in (3, 4):
            raise FoundationError("choice requires option; assignment needs citizen id")
        if verb == "choose":
            return ProductAction(layer, verb, option=parts[2])
        try:
            return ProductAction(layer, verb, target=int(parts[2]), option=parts[3])
        except ValueError as exc:
            raise FoundationError("resident identity is not an integer") from exc
    if verb in ("travel", "toggle", "tap", "move") or (
        layer == "studio" and verb == "gift"
    ):
        if len(parts) != 3:
            raise FoundationError("command requires numeric target")
        try:
            return ProductAction(layer, verb, target=int(parts[2]))
        except ValueError as exc:
            raise FoundationError("invalid action target") from exc
    try:
        return ProductAction(layer, verb, amount=int(parts[2]) if len(parts) == 3 else 1)
    except ValueError as exc:
        raise FoundationError("invalid action amount") from exc


def _interactive(state: ProductSession) -> ProductSession:
    print("Original World Product Studio — actual 2D tiles, citizens and systemic play.")
    print("Commands: terrain walk north; terrain forage; studio share_food;")
    print("living VERB; spatial VERB; mode VERB; causal end_turn; status; help; quit")
    while True:
        try:
            line = input("world> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGame session ended.")
            return state
        if line in ("quit", "exit"):
            return state
        if line in ("", "status", "map"):
            print(ascii_render(state.terrain, state.society))
            print(f"Actions remaining: {state.living.spatial.game.causal.action_points}; "
                  f"World turn: {state.living.living_turns}; local energy: {state.terrain.energy}")
            continue
        if line in ("missions", "quests"):
            print(json.dumps(mission_report(state), sort_keys=True, indent=2))
            continue
        if line == "help":
            law = validate_product(state)
            print("Living world commands:", ", ".join(law.foundation.system.commands))
            print("Genre controls:", ", ".join(law.source.advanced.mode.form.mechanics))
            print("Local verbs: walk, jump, chop, mine, forage, draw, bridge, dig,")
            print("build_hearth, build_mill, build_beacon, rest, eat")
            print("World: causal end_turn; studio: deposit_wood, deposit_stone, share_food")
            print("Social: studio gift ID or studio assign ID PROFESSION")
            continue
        try:
            action = parse_command(line, state.terrain.position)
            state, receipt = step_product(state, action)
            print(" | ".join(receipt.changes))
        except FoundationError as exc:
            print("Action rejected:", exc)


def _save(path: Path, state: ProductSession) -> None:
    if not path.parent.is_dir() or path.is_dir():
        raise FoundationError("save parent must exist and filename be writable")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(product_save(state), encoding="utf-8")
    temp.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Real original-game product pilot with physical terrain, "
                    "nonvisual world laws, twelve NPC jobs and native graphical option."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--index", type=int)
    selection.add_argument("--load", type=Path)
    selection.add_argument("--base", type=int)
    parser.add_argument("--form")
    parser.add_argument("--architecture")
    parser.add_argument("--system")
    parser.add_argument("--arc")
    parser.add_argument("--inhabitants", type=int, default=12)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--missions", action="store_true",
                        help="Evidence-based missions for the selected authored original root")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--desktop", action="store_true",
                        help="Launch actual native tkinter GUI if available")
    parser.add_argument("--show-map", action="store_true")
    parser.add_argument("--radius", type=int, default=8)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--ppm", type=Path)
    parser.add_argument("--save", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            print(json.dumps({
                "living": living_inventory(),
                "product": {
                    "local_terrain_chunk_size": 32,
                    "persistent_sparse_tile_edits": 2048,
                    "physical_citizen_professions": 12,
                    "native_gui": "Python tkinter desktop display required",
                    "renderers": ["SVG", "P6-PPM", "ASCII"],
                    "portable_build": "Python zipapp supported",
                    "native_console_packages": 0,
                    "individually_completed_games": 0,
                    "status": "integrated single-instance real-playable pilot",
                },
            }, indent=2, sort_keys=True))
            return 0
        if args.load is not None:
            if not args.load.is_file() or args.load.stat().st_size > 4194304:
                raise FoundationError("missing or oversized saved game")
            state = product_restore(args.load.read_text(encoding="utf-8"))
        elif args.base is not None:
            if not all((args.form, args.architecture, args.system, args.arc)):
                raise FoundationError("--base requires form, architecture, system and arc")
            law = living_for(args.base, args.form, args.architecture,
                             args.system, args.arc)
            state = create_product(law.index, inhabitants=args.inhabitants)
        else:
            if any((args.form, args.architecture, args.system, args.arc)):
                raise FoundationError("specify --base to select game dimensions")
            state = create_product(args.index if args.index is not None else 0,
                                   inhabitants=args.inhabitants)
        for action in parse_script(args.actions_json):
            state, _ = step_product(state, action)
        if args.interactive:
            state = _interactive(state)
        if args.desktop:
            from .original_world_product_desktop import launch_desktop
            launch_desktop(state, save_path=str(args.save) if args.save else None)
            if args.save:
                # A GUI save must be explicit; do not overwrite a newer GUI
                # session with the stale CLI snapshot after window dismissal.
                print("Native GUI controls its own save workflow.")
                return 0
        if args.save:
            _save(args.save, state)
        if args.svg:
            if not args.svg.parent.is_dir():
                raise FoundationError("SVG output directory does not exist")
            args.svg.write_text(svg_render(state.terrain, state.society,
                                           radius=args.radius), encoding="utf-8")
        if args.ppm:
            if not args.ppm.parent.is_dir():
                raise FoundationError("PPM output directory does not exist")
            args.ppm.write_bytes(ppm_render(state.terrain, state.society,
                                            radius=args.radius))
        if args.show_map:
            print(ascii_render(state.terrain, state.society, radius=args.radius))
        elif not args.desktop:
            law = validate_product(state)
            print(json.dumps({
                "world": law.as_dict(),
                "product": {
                    "position": state.terrain.position,
                    "local_energy": state.terrain.energy,
                    "physical_edits": len(state.terrain.edits),
                    "local_residents": len(state.society.inhabitants),
                    "world_turn": state.living.living_turns,
                    "player_events": state.events,
                    "real_gameplay_not_native_release": True,
                    "missions": mission_report(state) if args.missions else None,
                },
                "saved": str(args.save) if args.save else None,
                "renders": {
                    "svg": str(args.svg) if args.svg else None,
                    "ppm": str(args.ppm) if args.ppm else None,
                },
            }, sort_keys=True, indent=2))
    except (FoundationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
