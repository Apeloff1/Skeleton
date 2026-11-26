"""Offline interactive terminal player for canonical original grid campaigns.

This is a keyboard/text adapter, not a Godot or standalone desktop export.
Run: python -m skeleton.game.gameplay.offline_grid_player campaign.json saves/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session, GameplayContractError
from skeleton.game.gameplay.offline_grid_save import load_slot, save_slot

KEYS = {"w": "north", "a": "west", "s": "south", "d": "east"}
MAX_CAMPAIGN_BYTES = 65536


def read_campaign(path: Path) -> Campaign:
    if not path.is_file() or path.is_symlink():
        raise GameplayContractError("campaign must be a regular non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_CAMPAIGN_BYTES + 1)
    if len(raw) > MAX_CAMPAIGN_BYTES:
        raise GameplayContractError("campaign exceeds input budget")
    try:
        return Campaign.load(json.loads(raw))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GameplayContractError("invalid campaign JSON") from exc


def interpret(line: str, command_id: str) -> Command:
    if not isinstance(line, str) or len(line) > 128:
        raise GameplayContractError("invalid input length")
    tokens = line.strip().lower().split()
    if not tokens:
        raise GameplayContractError("empty command")
    if len(tokens) == 1 and tokens[0] in KEYS:
        return Command(command_id, "move", KEYS[tokens[0]])
    if len(tokens) == 1 and tokens[0] == "wait":
        return Command(command_id, "wait")
    if len(tokens) == 2 and tokens[0] in ("collect", "talk", "craft", "strike", "finish"):
        return Command(command_id, tokens[0], tokens[1])
    raise GameplayContractError("unknown player command")


def play(campaign: Campaign, saves: Path, *, input_fn: Callable[[str], str] = input,
         output: Callable[[str], None] = print) -> Session:
    """Run until victory/defeat or explicit quit; never silently overwrite a save."""
    session = Session.new(campaign)
    output("WASD move | collect/talk/craft/strike/finish ID | save SLOT | load SLOT | quit")
    while True:
        output(session.render())
        output(f"tick={session.tick} hp={session.health} quests={','.join(session.quests)}")
        if session.ending is not None:
            output(f"ENDING: {session.ending}")
            return session
        try:
            line = input_fn("> ").strip()
        except (EOFError, KeyboardInterrupt):
            output("Session ended without saving.")
            return session
        if line == "quit":
            return session
        parts = line.split()
        try:
            if len(parts) == 2 and parts[0] == "save":
                output(f"Saved {save_slot(saves, parts[1], session)}")
                continue
            if len(parts) == 2 and parts[0] == "load":
                session = load_slot(saves, parts[1], campaign)
                output(f"Restored tick {session.tick}")
                continue
            command = interpret(line, str(session.tick + 1))
            session = session.step(command)
        except (GameplayContractError, OSError, ValueError) as exc:
            output(f"Rejected: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play an original offline grid campaign")
    parser.add_argument("campaign", type=Path)
    parser.add_argument("saves", type=Path)
    args = parser.parse_args(argv)
    try:
        campaign = read_campaign(args.campaign)
        if not args.saves.is_dir() or args.saves.is_symlink():
            raise GameplayContractError("save directory must exist and not be a symlink")
        play(campaign, args.saves)
    except (GameplayContractError, OSError) as exc:
        parser.exit(2, f"Cannot start game: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
