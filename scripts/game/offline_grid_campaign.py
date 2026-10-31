"""Offline, deterministic grid campaign operator CLI.

Usage:
  python -m scripts.game.offline_grid_campaign inspect [--source FILE]
  python -m scripts.game.offline_grid_campaign run --commands FILE [--source FILE] [--resume FILE]
The run command prints a replay-verifiable JSON save to stdout; redirect to a file.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "skeleton/game/gameplay/content/lantern_harbor.json"
MAX_READ = 2_000_000


def _read(path: Path) -> object:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_READ:
            raise ValueError("not a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_READ + 1)
        if len(data) > MAX_READ:
            raise ValueError("input exceeds byte budget")
        return json.loads(data)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "run"))
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    try:
        campaign = Campaign.load(_read(args.source))
        if args.operation == "inspect":
            if args.commands or args.resume:
                raise ValueError("inspect does not accept commands or resume")
            session = Session.new(campaign)
            print(json.dumps({"source_digest": campaign.source_digest, "map": session.render(),
                              "title": campaign.spec["title"]}, sort_keys=True))
            return 0
        if args.commands is None:
            raise ValueError("run requires --commands")
        raw_commands = _read(args.commands)
        if not isinstance(raw_commands, list) or len(raw_commands) > 4096:
            raise ValueError("invalid command batch")
        session = Session.restore(campaign, _read(args.resume)) if args.resume else Session.new(campaign)
        for item in raw_commands:
            if not isinstance(item, dict) or set(item) - {"command_id", "kind", "target"}:
                raise ValueError("invalid command fields")
            session = session.step(Command(**item))
        print(json.dumps({"save": session.snapshot(), "map": session.render()}, sort_keys=True))
        return 0
    except (GameplayContractError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"offline-grid-campaign: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
