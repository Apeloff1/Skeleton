"""Offline CLI for canonical FLGB NPC schedules, replay and immutable saves."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import sys

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.npc_schedule import NpcCommand, NpcSchedule, NpcSession, play

MAX_JSON_BYTES = 2_000_000


def read_json(path: str) -> object:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise GameplayContractError("unsafe or oversized JSON source")
        with os.fdopen(os.dup(fd), "rb") as handle:
            data = handle.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise GameplayContractError("JSON source budget exceeded")
        return json.loads(data)
    finally:
        os.close(fd)


def save_new(path: str, data: bytes) -> None:
    if len(data) > MAX_JSON_BYTES:
        raise GameplayContractError("NPC save budget exceeded")
    target = Path(path)
    if target.name in ("", ".", ".."):
        raise GameplayContractError("invalid NPC save filename")
    directory = os.open(str(target.parent), os.O_RDONLY |
                        getattr(os, "O_DIRECTORY", 0) |
                        getattr(os, "O_NOFOLLOW", 0))
    temporary = ".npc-save-" + secrets.token_hex(12)
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory)
        created = True
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            raise
        os.link(temporary, target.name, src_dir_fd=directory,
                dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)



def interactive_session(session: NpcSession, player_id: str) -> NpcSession:
    """Drive a real offline terminal game; invalid moves never change state."""
    from skeleton.game.gameplay.flgb_gameplay_runtime import req_id

    req_id(player_id, "player_id")
    print("NPC world ready. Commands: look, facts, advance TICK, talk NPC INTERACTION, quit")
    for _ in range(8192):
        try:
            line = input("npc> ")
        except EOFError:
            break
        if len(line) > 256:
            print("rejected: command too long")
            continue
        words = line.split()
        if not words:
            continue
        if words[0] == "quit" and len(words) == 1:
            break
        if words[0] == "look" and len(words) == 1:
            print(json.dumps({"tick": session.tick,
                              "active": list(session.schedule.active(session.tick))},
                             sort_keys=True))
            continue
        if words[0] == "facts" and len(words) == 1:
            print(json.dumps({"facts": list(session.facts)}, sort_keys=True))
            continue
        try:
            if words[0] == "advance" and len(words) == 2:
                if not words[1].isascii() or not words[1].isdecimal():
                    raise GameplayContractError("invalid tick")
                command = NpcCommand("advance", int(words[1]))
            elif words[0] == "talk" and len(words) == 3:
                command = NpcCommand("interact", session.tick,
                                     words[1], words[2], player_id)
            else:
                raise GameplayContractError("unknown player command")
            session = session.apply(command)
            print(json.dumps({"tick": session.tick, "ending": session.ending,
                              "facts": list(session.facts),
                              "state_digest": session.state_digest}, sort_keys=True))
        except (GameplayContractError, ValueError) as exc:
            print(f"rejected: {exc}")
    return session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline source-bound NPC schedule replay")
    parser.add_argument("--schedule", required=True, help="Original authored NPC schedule JSON")
    parser.add_argument("--commands", help="JSON list of advance/interact commands")
    parser.add_argument("--resume", help="Previously saved verified NPC snapshot JSON")
    parser.add_argument("--save", help="Create a new immutable verified snapshot file")
    parser.add_argument("--interactive", action="store_true", help="Play using terminal commands")
    parser.add_argument("--player-id", default="player", help="Original player identity for interactions")
    parser.add_argument("--inspect-tick", type=int, help="Inspect NPC presence at a given tick")
    args = parser.parse_args(argv)
    try:
        schedule = NpcSchedule.parse(read_json(args.schedule))
        session = (NpcSession.restore(schedule, read_json(args.resume))
                   if args.resume else NpcSession.start(schedule))
        if args.commands:
            commands = read_json(args.commands)
            if type(commands) is not list:
                raise GameplayContractError("commands must be a JSON list")
            session = play(schedule, commands, session)
        if args.interactive:
            session = interactive_session(session, args.player_id)
        tick = session.tick if args.inspect_tick is None else args.inspect_tick
        result = {"world_id": schedule.world_id, "schedule_digest": schedule.digest,
                  "tick": session.tick, "ending": session.ending,
                  "state_digest": session.state_digest,
                  "facts": list(session.facts), "events_digest": session.events.digest,
                  "active": list(schedule.active(tick)), "inspected_tick": tick}
        if args.save:
            snapshot = session.snapshot()
            save_new(args.save, (json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
                                 + "\n").encode("utf-8"))
            result["save_digest"] = snapshot["save_digest"]
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"NPC schedule rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
