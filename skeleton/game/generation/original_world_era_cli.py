"""Playable era/theology reference world with real technology and rite actions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_world_campaign import ACTION_MECHANICS, CampaignAction, CampaignError, SCENARIOS
from .original_world_campaign_cli import _parse_terminal as parse_world
from .original_world_campaign_cli import render as world_map
from .original_world_era_runtime import (
    RITUAL_ACTIONS, TECH_ACTIONS, StyledAction,
    create_styled_world, styled_restore, styled_save, styled_step,
)
from .world_styling import WorldStyling

MAX_SCRIPT = 65536


def _parse_script(source: str):
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SCRIPT:
        raise CampaignError("invalid or oversized era action script")
    try:
        payload = json.loads(source)
    except (TypeError, ValueError) as exc:
        raise CampaignError("invalid action JSON") from exc
    if not isinstance(payload, list) or len(payload) > 1024:
        raise CampaignError("era actions must be a bounded list")
    actions = []
    for row in payload:
        if not isinstance(row, dict):
            raise CampaignError("invalid era action record")
        if "tech" in row or "ritual" in row:
            category = "tech" if "tech" in row else "ritual"
            if set(row) - {category, "amount"}:
                raise CampaignError("unknown styled action fields")
            verb = row[category]
            valid = TECH_ACTIONS if category == "tech" else RITUAL_ACTIONS
            if verb not in valid:
                raise CampaignError("unsupported technology or ritual")
            actions.append(StyledAction(verb, row.get("amount", 1)))
        elif "verb" in row:
            if set(row) - {"verb", "target", "amount", "option"}:
                raise CampaignError("unknown gameplay action fields")
            action = CampaignAction(**row)
            if action.verb not in ACTION_MECHANICS:
                raise CampaignError("unimplemented world action")
            actions.append(action)
        else:
            raise CampaignError("unknown styled action type")
    return tuple(actions)


def _parse_command(line: str):
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise CampaignError("invalid command quoting") from exc
    if not parts:
        raise CampaignError("empty command")
    if parts[0] in ("tech", "ritual"):
        if not 2 <= len(parts) <= 3:
            raise CampaignError("use tech VERB [AMOUNT] or ritual VERB [AMOUNT]")
        valid = TECH_ACTIONS if parts[0] == "tech" else RITUAL_ACTIONS
        if parts[1] not in valid:
            raise CampaignError("unrecognized technology or ritual")
        try:
            amount = int(parts[2]) if len(parts) == 3 else 1
        except ValueError as exc:
            raise CampaignError("invalid quantity") from exc
        return StyledAction(parts[1], amount)
    return parse_world(line)


def _render(session) -> str:
    return "\n".join([
        world_map(session.world),
        f"Era: {session.styling.era} "
        f"(tech tier {TECH_ACTIONS.get('knap', 0)}–{max(TECH_ACTIONS.values())})",
        f"Cosmology: {session.styling.theology} | "
        f"Chronology: {session.styling.chronology}",
        f"Comfort {session.styling.comfort}/100 | "
        f"Requested realism {session.styling.realism}/100",
        f"Metal {session.metal} | Machines {session.machinery} | "
        f"Grid {session.grid_power} | Robots {session.robots} | Drones {session.probes}",
        f"Devotion {session.devotion} | Heritage {session.heritage} | "
        f"Omen {session.last_vision or 'none'} | Loops {session.loops}",
    ])


def _interactive(session):
    print("Original era-world pilot. Commands: map, status, help, quit, tech, ritual.")
    print(_render(session))
    while True:
        try:
            line = input("era> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEra session closed.")
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line in ("map", "status"):
            print(_render(session))
            continue
        if line == "help":
            print("Technology:", ", ".join(sorted(TECH_ACTIONS)))
            print("Rituals:", ", ".join(sorted(RITUAL_ACTIONS)))
            print("Other world verbs:", ", ".join(sorted(ACTION_MECHANICS)))
            continue
        try:
            session, receipt = styled_step(session, _parse_command(line))
            print(" | ".join(receipt.effects))
            print(_render(session))
        except CampaignError as exc:
            print("Action rejected:", exc)
    return session


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play era and invented theology mechanics.")
    parser.add_argument("--world", choices=sorted(SCENARIOS), default="serenity-05")
    parser.add_argument("--seed", default="era-demo")
    parser.add_argument("--era", default="iron-age")
    parser.add_argument("--chronology", default="fictional-history")
    parser.add_argument("--theology", default="none")
    parser.add_argument("--theme", action="append", dest="themes")
    parser.add_argument("--visual-style", default="stylized-pbr")
    parser.add_argument("--tone", default="adventurous")
    parser.add_argument("--simulation-realism", default="systemic-lite")
    parser.add_argument("--hardware-target", default="pc-windows")
    parser.add_argument("--comfort", type=int, default=50)
    parser.add_argument("--realism", type=int, default=50)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--load", type=Path)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--show-map", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.load:
            if not args.load.is_file() or args.load.stat().st_size > 524288:
                raise CampaignError("invalid or oversized styled save")
            session = styled_restore(args.load.read_text(encoding="utf-8"))
        else:
            style = WorldStyling(
                era=args.era, chronology=args.chronology,
                theology=args.theology,
                themes=tuple(args.themes or ("exploration",)),
                visual_style=args.visual_style, tone=args.tone,
                simulation_realism=args.simulation_realism,
                hardware_target=args.hardware_target,
                comfort=args.comfort, realism=args.realism,
            )
            session = create_styled_world(args.world, args.seed, style)
        for action in _parse_script(args.actions_json):
            session, _ = styled_step(session, action)
        if args.interactive:
            session = _interactive(session)
        if args.save:
            if not args.save.parent.is_dir() or args.save.is_dir():
                raise CampaignError("invalid styled save destination")
            temporary = args.save.with_name(args.save.name + ".tmp")
            temporary.write_text(styled_save(session), encoding="utf-8")
            temporary.replace(args.save)
        if not args.interactive:
            if args.show_map:
                print(_render(session))
            else:
                print(json.dumps({
                    "status": "playable-abstract-era-and-cosmology",
                    "world": session.world.world_id,
                    "styling": session.styling.as_dict(),
                    "technology": {"metal": session.metal, "machinery": session.machinery,
                                   "power": session.grid_power, "robots": session.robots,
                                   "probes": session.probes},
                    "theology": {"devotion": session.devotion, "heritage": session.heritage,
                                 "visions": session.visions,
                                 "last_vision": session.last_vision},
                    "chronology": {"turn": session.world.turn, "loops": session.loops},
                    "event_count": session.events,
                    "note": "Style-aware abstract rules; no verified native render build.",
                }, sort_keys=True, indent=2))
    except (CampaignError, ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
