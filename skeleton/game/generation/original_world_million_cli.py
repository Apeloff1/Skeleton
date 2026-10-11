"""Offline interactive million-world genre/progression reference game.

Index and filters resolve *causal* game components, not procedural assets or
unverified console builds. Multi-hour worlds require separate production
rendering/physics adapters; this terminal is a playable bounded prototype.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_foundation_compiler import FoundationError
from .original_world_million_compiler import (
    ADVANCED_CONFIGURATIONS, advanced_at, advanced_for,
    advanced_from_seed, advanced_inventory, page_advanced,
)
from .original_world_million_runtime import (
    AdvancedAction, AdvancedState, create_advanced, step_advanced,
    restore_advanced, save_advanced, validate_game, LAYERS,
)
from .original_world_play_forms import PLAY_FORMS, PROGRESSION_LAWS
from .original_world_million_objectives import (
    objective_report, guided_next_action,
)

MAX_SCRIPT_BYTES = 65536


def parse_advanced_script(source: str) -> tuple[AdvancedAction, ...]:
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise FoundationError("invalid or oversized action script")
    try:
        value = json.loads(source)
    except (ValueError, TypeError) as exc:
        raise FoundationError("invalid advanced game JSON") from exc
    if not isinstance(value, list) or len(value) > 1000:
        raise FoundationError("script requires a bounded array")
    actions = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - {
            "layer", "verb", "amount", "option", "target",
        }:
            raise FoundationError("unknown advanced action fields")
        try:
            action = AdvancedAction(**entry)
        except (TypeError, ValueError) as exc:
            raise FoundationError("malformed game action") from exc
        if action.layer not in LAYERS:
            raise FoundationError("invalid game command layer")
        actions.append(action)
    return tuple(actions)


def parse_advanced_command(line: str) -> AdvancedAction:
    try:
        words = shlex.split(line)
    except ValueError as exc:
        raise FoundationError("invalid terminal quotation") from exc
    if not 2 <= len(words) <= 4 or words[0] not in LAYERS:
        raise FoundationError("use: [causal|mode|arc] VERB [TARGET|AMOUNT]")
    layer, verb = words[:2]
    if verb == "choose":
        if len(words) != 3:
            raise FoundationError("choose requires care or power")
        return AdvancedAction(layer, verb, option=words[2])
    if verb == "toggle" or verb == "tap" or (layer == "causal" and verb == "move"):
        if len(words) != 3:
            raise FoundationError("command requires an explicit target")
        try:
            return AdvancedAction(layer, verb, target=int(words[2]))
        except ValueError as exc:
            raise FoundationError("invalid target number") from exc
    if len(words) > 3:
        raise FoundationError("command takes at most one quantity")
    try:
        return AdvancedAction(
            layer, verb, int(words[2]) if len(words) == 3 else 1,
        )
    except ValueError as exc:
        raise FoundationError("invalid quantity") from exc


def render_advanced(state: AdvancedState) -> str:
    law = validate_game(state)
    mode, arc, world = state.mode, state.arc, state.causal
    return "\n".join((
        f"Advanced original world: {law.mode.base.title}",
        f"Gameplay form: {law.mode.form.title} [{law.mode.form.form_id}]",
        f"Progression: {law.arc.title} [{law.arc.arc_id}]",
        f"Authored law: {law.mode.base.root.invariant}",
        f"Consequences: {law.mode.base.coupling}",
        f"Turn {world.tick} | AP {world.action_points} | Energy {world.energy} | Supplies {world.supplies}",
        f"Trust {world.trust} | Evidence {world.evidence} | Causal progress {world.primary}",
        f"Form: course {mode.course}, puzzle bits {mode.switches}, enemy {mode.enemy}, "
        f"water {mode.water}, homes {mode.housing}, colony {mode.population}, "
        f"track {mode.distance}, guard alert {mode.alert}, market funds {mode.wallet}, "
        f"explored {len(mode.revealed)}, rhythm combo {mode.combo}",
        f"Arc: chapter {arc.chapter} | legacy {arc.legacy} | runs {arc.attempts} | "
        f"generation {arc.generation} | outstanding aid {arc.outstanding} | "
        f"branch {arc.branch or 'none'}",
        f"Genre objective {'completed' if mode.cleared else 'ongoing'}, "
        f"arc {'completed' if arc.completed else 'ongoing'}; "
        f"continuation {law.arc.continuation_policy}",
        "Next action: " + guided_next_action(state),
        "This is a genre-specific abstract reference game, not verified native software.",
    ))


def _interactive(state: AdvancedState) -> AdvancedState:
    print("Original Million-World Forge — terminal reference game.")
    print("Commands: status, objectives, help, quit; mode VERB, arc VERB, causal VERB.")
    print(render_advanced(state))
    while True:
        try:
            command = input("forge> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nWorld session ended.")
            break
        if command in ("quit", "exit"):
            break
        if not command:
            continue
        if command in ("status", "map"):
            print(render_advanced(state))
            continue
        if command in ("objectives", "quests"):
            print(json.dumps(objective_report(state), sort_keys=True, indent=2))
            continue
        if command == "help":
            law = validate_game(state)
            print("Genre actions:", ", ".join(law.mode.form.mechanics))
            print("Progression: commit, aid, investigate, choose, reflect")
            print("World: intervene, study, negotiate, restore, move, end_turn, ...")
            print("Examples: mode jump 2 | arc aid | causal end_turn")
            continue
        try:
            state, receipt = step_advanced(state, parse_advanced_command(command))
            print(" | ".join(receipt.changes))
            print(render_advanced(state))
        except FoundationError as exc:
            print("Action rejected:", exc)
    return state


def _write_save(path: Path, state: AdvancedState) -> None:
    if not path.parent.is_dir() or path.is_dir():
        raise FoundationError("save parent must exist and destination must be a file")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(save_advanced(state), encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Browse 102,400 form-bound game foundations and play 1,228,800 advanced configurations."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--index", type=int)
    selection.add_argument("--seed")
    selection.add_argument("--load", type=Path)
    selection.add_argument("--base", type=int, help="Index of authored-law foundation [0..10239]")
    parser.add_argument("--form", choices=tuple(f.form_id for f in PLAY_FORMS))
    parser.add_argument("--arc", choices=tuple(a.arc_id for a in PROGRESSION_LAWS))
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--objectives", action="store_true",
                        help="Include a live proof-based quest ledger")
    parser.add_argument("--page", type=int)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--save", type=Path)
    parser.add_argument("--show-map", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            print(json.dumps(advanced_inventory(), sort_keys=True, indent=2))
            return 0
        if args.page is not None:
            if any(x is not None for x in (
                args.base, args.index, args.seed, args.load, args.form, args.arc,
            )):
                raise FoundationError("paging cannot mix with another world selector")
            entries = list(page_advanced(start=args.page, limit=args.limit))
            print(json.dumps({
                "total": str(ADVANCED_CONFIGURATIONS),
                "start": str(args.page),
                "entries": [{
                    "index": str(x.index), "id": x.advanced_id,
                    "base_index": str(x.mode.base.foundation_index),
                    "form": x.mode.form.form_id, "arc": x.arc.arc_id,
                    "design_id": x.design_id,
                    "provenance": x.provenance,
                } for x in entries],
            }, sort_keys=True, indent=2))
            return 0
        if args.load:
            if not args.load.is_file() or args.load.stat().st_size > 131072:
                raise FoundationError("missing or oversized save")
            state = restore_advanced(args.load.read_text(encoding="utf-8"))
        else:
            if args.base is not None:
                if not args.form or not args.arc:
                    raise FoundationError("--base requires both --form and --arc")
                law = advanced_for(args.base, args.form, args.arc)
            else:
                if args.form or args.arc:
                    raise FoundationError("select --base to specify form and arc")
                law = (advanced_at(args.index) if args.index is not None
                       else advanced_from_seed(args.seed or "original-million-default"))
            state = create_advanced(law.advanced_id)
        for action in parse_advanced_script(args.actions_json):
            state, _ = step_advanced(state, action)
        if args.interactive:
            state = _interactive(state)
        if args.save:
            _write_save(args.save, state)
        if not args.interactive:
            if args.show_map:
                print(render_advanced(state))
            else:
                law = validate_game(state)
                print(json.dumps({
                    "configuration": law.as_dict(),
                    "game": json.loads(save_advanced(state))["payload"],
                    "status": "bounded-reference-game",
                    "objectives": objective_report(state) if args.objectives else None,
                    "next_action": guided_next_action(state),
                    "note": "No per-configuration bespoke native game is implied by index.",
                }, sort_keys=True, indent=2, ensure_ascii=False))
    except (FoundationError, ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
