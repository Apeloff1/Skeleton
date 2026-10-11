"""Offline 12.288m-world architecture browser and playable terminal.

No game binaries/assets, network services, console SDKs or proprietary code
are produced. The spatial/gameplay/progression laws are a bounded deterministic
reference game; enormous index cardinality never implies complete games.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_foundation_compiler import FoundationError
from .original_world_tenfold_architectures import ARCHITECTURES
from .original_world_tenfold_compiler import (
    TENFOLD_CONFIGURATIONS, tenfold_at, tenfold_for, tenfold_from_seed,
    page_tenfold, tenfold_inventory,
)
from .original_world_tenfold_runtime import (
    TenfoldAction, TenfoldState, create_tenfold, passages, site_capacity,
    available_material, save_tenfold, restore_tenfold, step_tenfold,
    validate_tenfold,
)
from .original_world_play_forms import PLAY_FORMS, PROGRESSION_LAWS

MAX_INPUT = 65536


def script_actions(text: str) -> tuple[TenfoldAction, ...]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT:
        raise FoundationError("script exceeds bounded action budget")
    try:
        records = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise FoundationError("invalid action JSON") from exc
    if not isinstance(records, list) or len(records) > 1000:
        raise FoundationError("script must be a bounded list")
    actions = []
    for item in records:
        if not isinstance(item, dict) or set(item) - {
            "layer", "verb", "amount", "target", "option",
        }:
            raise FoundationError("invalid action structure")
        try:
            actions.append(TenfoldAction(**item))
        except (TypeError, ValueError) as exc:
            raise FoundationError("malformed world action") from exc
    return tuple(actions)


def parse_command(value: str) -> TenfoldAction:
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise FoundationError("invalid action quoting") from exc
    if not 2 <= len(tokens) <= 3:
        raise FoundationError("command format: LAYER VERB [TARGET|AMOUNT]")
    layer, verb = tokens[:2]
    if layer not in ("spatial", "causal", "mode", "arc"):
        raise FoundationError("unknown gameplay layer")
    if verb == "choose":
        if len(tokens) != 3:
            raise FoundationError("choose requires explicit care or power")
        return TenfoldAction(layer, verb, option=tokens[2])
    if verb in ("travel", "move", "toggle", "tap"):
        if len(tokens) != 3:
            raise FoundationError("target required")
        try:
            return TenfoldAction(layer, verb, target=int(tokens[2]))
        except ValueError as exc:
            raise FoundationError("noninteger world target") from exc
    try:
        return TenfoldAction(layer, verb,
                             amount=int(tokens[2]) if len(tokens) == 3 else 1)
    except ValueError as exc:
        raise FoundationError("invalid command quantity") from exc


def render(state: TenfoldState) -> str:
    world = validate_tenfold(state)
    arch = world.spatial.architecture
    game = state.game
    return "\n".join((
        f"{arch.title} — {world.advanced.mode.base.root.title}",
        f"Play form: {world.advanced.mode.form.form_id}, "
        f"continuation: {world.advanced.arc.arc_id}",
        f"Spatial law: {arch.spatial_contract}",
        f"Action: {arch.intervention}; hazard: {arch.hazard_model}",
        f"Spatial node {state.position}/23, exits {passages(state)}; "
        f"visited {len(state.visited)}/24, surveyed {len(state.surveyed)}/24",
        f"Geological reserve {available_material(state)}; "
        f"stored materials {state.materials}, oxygen {state.oxygen}, "
        f"fuel {state.fuel}, danger {state.danger}",
        f"Game energy {game.causal.energy}, supply {game.causal.supplies}, "
        f"trust {game.causal.trust}, evidence {game.causal.evidence}, "
        f"remaining actions {game.causal.action_points}",
        f"Turn {state.tick}, events {state.events}, "
        f"genre score/actions {game.mode.music_score}/{game.mode.actions}, "
        f"chapter {game.arc.chapter}, postgame {'yes' if game.mode.cleared else 'no'}",
        "Reference spatial and genre simulation. Not a verified native game.",
    ))


def _interactive(game: TenfoldState) -> TenfoldState:
    print("Original Tenfold World Forge — spatial/genre/progression simulator.")
    print("Commands: spatial travel N, spatial extract, spatial INTERVENTION,")
    print("mode VERB, arc VERB, causal end_turn; help, status, exits, quit.")
    print(render(game))
    while True:
        try:
            text = input("tenfold> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSpatial world session closed.")
            break
        if not text:
            continue
        if text in ("quit", "exit"):
            break
        if text in ("status", "map", "exits"):
            print(render(game))
            continue
        if text == "help":
            law = validate_tenfold(game)
            print("World construction command:", law.spatial.architecture.intervention)
            print("Genre controls:", ", ".join(law.advanced.mode.form.mechanics))
            print("Available links:", passages(game))
            continue
        try:
            game, receipt = step_tenfold(game, parse_command(text))
            print(" | ".join(receipt.changes))
            print(render(game))
        except FoundationError as exc:
            print("Action rejected:", exc)
    return game


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play one of 12,288,000 spatial/gameplay/arc reference configurations."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--index", type=int)
    selector.add_argument("--seed")
    selector.add_argument("--load", type=Path)
    selector.add_argument("--base", type=int)
    parser.add_argument("--form", choices=tuple(f.form_id for f in PLAY_FORMS))
    parser.add_argument("--architecture", choices=tuple(
        a.architecture_id for a in ARCHITECTURES))
    parser.add_argument("--arc", choices=tuple(a.arc_id for a in PROGRESSION_LAWS))
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--page", type=int)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--show-map", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--save", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            print(json.dumps(tenfold_inventory(), sort_keys=True, indent=2))
            return 0
        if args.page is not None:
            if any(x is not None for x in (
                args.base, args.index, args.seed, args.load,
                args.form, args.architecture, args.arc,
            )):
                raise FoundationError("paging cannot combine exact source selections")
            entries = list(page_tenfold(start=args.page, limit=args.limit))
            print(json.dumps({
                "size": str(TENFOLD_CONFIGURATIONS),
                "start": str(args.page),
                "entries": [{
                    "index": str(x.index),
                    "world_id": x.tenfold_id,
                    "original_source": x.advanced.mode.base.foundation_id,
                    "form": x.advanced.mode.form.form_id,
                    "space": x.spatial.architecture.architecture_id,
                    "arc": x.advanced.arc.arc_id,
                    "design_id": x.design_id,
                } for x in entries],
            }, sort_keys=True, indent=2))
            return 0
        if args.load is not None:
            if not args.load.is_file() or args.load.stat().st_size > 262144:
                raise FoundationError("unavailable or oversized world save")
            game = restore_tenfold(args.load.read_text(encoding="utf-8"))
        else:
            if args.base is not None:
                if not (args.form and args.architecture and args.arc):
                    raise FoundationError("base selection needs form, architecture and arc")
                world = tenfold_for(args.base, args.form, args.architecture, args.arc)
            else:
                if args.form or args.architecture or args.arc:
                    raise FoundationError("specify --base when selecting world architecture")
                world = tenfold_at(args.index) if args.index is not None else tenfold_from_seed(
                    args.seed or "tenfold-reference-world")
            game = create_tenfold(world.index)
        for action in script_actions(args.actions_json):
            game, _ = step_tenfold(game, action)
        if args.interactive:
            game = _interactive(game)
        if args.save is not None:
            if not args.save.parent.is_dir() or args.save.is_dir():
                raise FoundationError("save directory must exist and be writable")
            temp = args.save.with_name(args.save.name + ".tmp")
            temp.write_text(save_tenfold(game), encoding="utf-8")
            temp.replace(args.save)
        if not args.interactive:
            if args.show_map:
                print(render(game))
            else:
                world = validate_tenfold(game)
                print(json.dumps({
                    "world": world.as_dict(),
                    "state": json.loads(save_tenfold(game))["payload"],
                    "current_passages": passages(game),
                    "mineral_reserve_at_current_site": available_material(game),
                    "implementation_status": "bounded-spatial-genre-simulation",
                    "note": "Indexing 12.288m gameplay compositions does not create 12.288m bespoke games.",
                }, sort_keys=True, indent=2))
    except (FoundationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
