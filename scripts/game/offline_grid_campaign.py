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
import tempfile

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Command, Session
from skeleton.game.gameplay.grid_viewport import viewport

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


def _write_new_save(path: Path, snapshot: dict) -> None:
    """Publish a verified replay snapshot without replacing an existing save slot."""
    data = (json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_READ:
        raise ValueError("save exceeds byte budget")
    fd, temporary = tempfile.mkstemp(prefix=".campaign-save-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "run", "play", "solve"))
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--out-save", type=Path, help="Create a durable no-clobber replay save")
    parser.add_argument("--view-width", type=int, default=11)
    parser.add_argument("--view-height", type=int, default=9)
    parser.add_argument("--accessible", action="store_true")
    parser.add_argument("--goal-ending")
    parser.add_argument("--max-nodes", type=int, default=1024)
    parser.add_argument("--max-depth", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        campaign = Campaign.load(_read(args.source))
        camera = viewport(Session.new(campaign), args.view_width, args.view_height)
        if args.operation == "solve":
            if args.commands or args.resume or args.out_save or not args.goal_ending:
                raise ValueError("solve requires goal and forbids commands/resume")
            from skeleton.game.gameplay.grid_playthrough_route import plan_playthrough
            result = plan_playthrough(
                campaign, args.goal_ending,
                max_nodes=args.max_nodes, max_depth=args.max_depth,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args.goal_ending is not None or args.max_nodes != 1024 or args.max_depth != 64:
            raise ValueError("route options require solve")
        if args.operation == "inspect":
            if args.commands or args.resume or args.out_save:
                raise ValueError("inspect does not accept commands or resume")
            session = Session.new(campaign)
            print(json.dumps({"source_digest": campaign.source_digest, "map": session.render(),
                              "viewport": camera.record(),
                              "title": campaign.spec["title"]}, sort_keys=True))
            return 0
        if args.operation == "play":
            if args.commands is not None:
                raise ValueError("play reads commands from the terminal")
            session = Session.restore(campaign, _read(args.resume)) if args.resume else Session.new(campaign)
            print("Offline grid campaign: move north/south/east/west, collect ID, talk ID, finish ID, wait, quit")
            while session.ending is None and session.tick < 4096:
                camera = viewport(session, args.view_width, args.view_height)
                print(camera.description if args.accessible else camera.render())
                try:
                    line = input("> ").strip()
                except EOFError:
                    break
                if line == "quit":
                    break
                parts = line.split()
                if not parts or len(parts) > 2:
                    print("Enter a command and optional target.", file=sys.stderr)
                    continue
                kind = parts[0]
                target = parts[1] if len(parts) == 2 else ""
                try:
                    session = session.step(Command(f"terminal-{session.tick + 1}", kind, target))
                except GameplayContractError as exc:
                    print(f"Rejected: {exc}", file=sys.stderr)
            if args.out_save is not None:
                _write_new_save(args.out_save, session.snapshot())
            print()
            print(json.dumps({"save": session.snapshot(), "map": session.render(),
                              "viewport": viewport(session, args.view_width, args.view_height).record()},
                             sort_keys=True))
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
        if args.out_save is not None:
            _write_new_save(args.out_save, session.snapshot())
        print(json.dumps({"save": session.snapshot(), "map": session.render(),
                          "viewport": viewport(session, args.view_width, args.view_height).record()},
                         sort_keys=True))
        return 0
    except (GameplayContractError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"offline-grid-campaign: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
