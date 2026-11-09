"""Offline 122.88m living-world browser, executable studio and save-game CLI.

The input namespace addresses causal law × genre × architecture × autonomous
system × progression. Each mode has unique state transitions and finite
physical consequences, but is a bounded text simulation, NOT a shipped game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_foundation_compiler import FoundationError
from .original_world_living_10x_compiler import (
    LIVING_CONFIGURATIONS, living_at, living_for, living_from_seed,
    living_inventory, page_living,
)
from .original_world_living_10x_runtime import (
    ACTIVE_LAYERS, LivingAction, LivingState, create_living,
    restore_living, save_living, step_living, validate_living,
)
from .original_world_living_systems import SYSTEMS
from .original_world_play_forms import PLAY_FORMS, PROGRESSION_LAWS
from .original_world_tenfold_architectures import ARCHITECTURES
from .original_world_tenfold_runtime import passages
from .original_world_living_10x_objectives import living_objectives

MAX_SCRIPT_BYTES = 65536


def parse_script(text: str) -> tuple[LivingAction, ...]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise FoundationError("living command script exceeds bounded budget")
    try:
        commands = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise FoundationError("living command script is not valid JSON") from exc
    if not isinstance(commands, list) or len(commands) > 1000:
        raise FoundationError("living actions must be a bounded command array")
    output = []
    for cmd in commands:
        if not isinstance(cmd, dict) or set(cmd) - {
            "layer", "verb", "amount", "target", "option",
        }:
            raise FoundationError("unknown scripted player-action property")
        try:
            action = LivingAction(**cmd)
        except (TypeError, ValueError) as exc:
            raise FoundationError("invalid typed scripted player action") from exc
        if (action.layer not in ACTIVE_LAYERS or
                type(action.amount) is not int or not 1 <= action.amount <= 3 or
                type(action.target) is not int or not -1 <= action.target <= 23 or
                not isinstance(action.verb, str) or not 0 < len(action.verb) <= 64 or
                not isinstance(action.option, str) or len(action.option) > 32):
            raise FoundationError("script contains untrusted action schema")
        output.append(action)
    return tuple(output)


def parse_command(line: str) -> LivingAction:
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise FoundationError("invalid terminal action quotation") from exc
    if not 2 <= len(parts) <= 3 or parts[0] not in ACTIVE_LAYERS:
        raise FoundationError("command format: LAYER VERB [TARGET|AMOUNT]")
    layer, verb = parts[:2]
    if verb == "choose":
        if len(parts) != 3:
            raise FoundationError("choice requires care/power option")
        return LivingAction(layer, verb, option=parts[2])
    if verb in ("travel", "move", "toggle", "tap"):
        if len(parts) != 3:
            raise FoundationError("movement or switch requires target")
        try:
            return LivingAction(layer, verb, target=int(parts[2]))
        except ValueError as exc:
            raise FoundationError("noninteger action target") from exc
    try:
        return LivingAction(
            layer, verb, amount=(int(parts[2]) if len(parts) == 3 else 1),
        )
    except ValueError as exc:
        raise FoundationError("noninteger living-world quantity") from exc


def render(state: LivingState) -> str:
    law = validate_living(state)
    system, source, m = law.foundation.system, state.spatial, state.metrics
    return "\n".join((
        f"{system.title}: {law.source.advanced.mode.base.root.title}",
        f"Authored world law: {law.source.advanced.mode.base.root.invariant}",
        f"Spatial architecture: {law.source.spatial.architecture.title}",
        f"Play: {law.source.advanced.mode.form.form_id}; "
        f"continuation: {law.source.advanced.arc.arc_id}",
        f"Actors: {system.actor_model}",
        f"Autonomous clock: {system.autonomous_process}",
        f"Player commands: {', '.join(system.commands)}",
        f"World tick {state.living_turns}, events {state.events}; "
        f"position {source.position}/23, exits {passages(source)}",
        f"AP {source.game.causal.action_points}; "
        f"stamina {source.game.causal.energy}, supplies {source.game.causal.supplies}, "
        f"material {source.materials}, fuel {source.fuel}, world danger {source.danger}",
        f"Population: grazers {m.grazers}, predators {m.predators}; "
        f"households {m.households}/{m.housing}; "
        f"organisms {m.unaffected}/{m.affected}/{m.recovered}",
        f"Economy: cargo {m.cargo}, in transit {m.in_transit}, delivered {m.delivered}; "
        f"reservoir {m.reservoir}, power reserve {m.battery}",
        f"Automation: robots {m.builders}, orders {m.orders}, built {m.completed}; "
        f"facts {m.proven}, shared {m.shared}",
        f"Next need: {living_objectives(state)['next_action']}",
        f"Society: treaty tension {m.tension}, obligations {m.promises}; "
        f"temporal echoes {m.queued_echoes}, debt {m.time_debt}",
        "This is a bounded living-systems reference game, not a native 3D release.",
    ))


def interactive(state: LivingState) -> LivingState:
    print("Living Original World Studio — autonomous systems and nested world play.")
    print("Commands: living VERB; spatial VERB; mode VERB; arc VERB;")
    print("causal end_turn; goals, help, status, quit.")
    print(render(state))
    while True:
        try:
            line = input("living-world> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLiving world session closed.")
            break
        if line in ("quit", "exit"):
            break
        if not line:
            continue
        if line in ("status", "map"):
            print(render(state))
            continue
        if line in ("goals", "objectives"):
            print(json.dumps(living_objectives(state), sort_keys=True, indent=2))
            continue
        if line == "help":
            law = validate_living(state)
            print("System commands:", ", ".join(law.foundation.system.commands))
            print("Genre commands:", ", ".join(law.source.advanced.mode.form.mechanics))
            print("World traversals:", passages(state.spatial))
            print("The autonomous world clock advances on 'causal end_turn'.")
            continue
        try:
            state, receipt = step_living(state, parse_command(line))
            print(" | ".join(receipt.changes))
            print(render(state))
        except FoundationError as exc:
            print("Action rejected:", exc)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play an authored-rule composition among 122,880,000 living reference worlds."
    )
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument("--index", type=int)
    exclusive.add_argument("--seed")
    exclusive.add_argument("--load", type=Path)
    exclusive.add_argument("--base", type=int)
    parser.add_argument("--form", choices=[x.form_id for x in PLAY_FORMS])
    parser.add_argument("--architecture",
                        choices=[x.architecture_id for x in ARCHITECTURES])
    parser.add_argument("--system", choices=[x.system_id for x in SYSTEMS])
    parser.add_argument("--arc", choices=[x.arc_id for x in PROGRESSION_LAWS])
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--objectives", action="store_true",
                        help="Show evidence-backed living-system goals and crises")
    parser.add_argument("--page", type=int)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--show-map", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--save", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            print(json.dumps(living_inventory(), sort_keys=True, indent=2))
            return 0
        if args.page is not None:
            if any(x is not None for x in (
                args.base, args.index, args.seed, args.load, args.form,
                args.architecture, args.system, args.arc,
            )):
                raise FoundationError("pagination cannot combine with a world selector")
            worlds = list(page_living(start=args.page, limit=args.limit))
            print(json.dumps({
                "total": str(LIVING_CONFIGURATIONS),
                "start": str(args.page),
                "worlds": [{
                    "index": str(w.index), "id": w.world_id,
                    "source_tenfold_index": str(w.source.index),
                    "system": w.foundation.system.system_id,
                    "genre": w.source.advanced.mode.form.form_id,
                    "architecture": w.source.spatial.architecture.architecture_id,
                    "arc": w.source.advanced.arc.arc_id,
                    "design_id": w.design_id,
                } for w in worlds],
            }, indent=2, sort_keys=True))
            return 0
        if args.load is not None:
            if not args.load.is_file() or args.load.stat().st_size > 524288:
                raise FoundationError("save missing or exceeds supported size")
            state = restore_living(args.load.read_text(encoding="utf-8"))
        else:
            if args.base is not None:
                if not all((args.form, args.architecture, args.system, args.arc)):
                    raise FoundationError("base selection needs form, architecture, system, arc")
                law = living_for(args.base, args.form, args.architecture,
                                 args.system, args.arc)
            else:
                if any((args.form, args.architecture, args.system, args.arc)):
                    raise FoundationError("use --base when selecting individual world systems")
                law = living_at(args.index) if args.index is not None else living_from_seed(
                    args.seed or "living-world-default")
            state = create_living(law.index)
        for action in parse_script(args.actions_json):
            state, _ = step_living(state, action)
        if args.interactive:
            state = interactive(state)
        if args.save is not None:
            if not args.save.parent.is_dir() or args.save.is_dir():
                raise FoundationError("world save parent must exist")
            temp = args.save.with_name(args.save.name + ".tmp")
            temp.write_text(save_living(state), encoding="utf-8")
            temp.replace(args.save)
        if not args.interactive:
            if args.show_map:
                print(render(state))
            else:
                law = validate_living(state)
                print(json.dumps({
                    "world": law.as_dict(),
                    "world_state": json.loads(save_living(state))["payload"],
                    "implementation_status": "bounded-autonomous-world-simulation",
                    "objectives": living_objectives(state) if args.objectives else None,
                    "note": "12.288e7 compositions do not imply separate full native games.",
                }, ensure_ascii=False, sort_keys=True, indent=2))
    except (FoundationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
