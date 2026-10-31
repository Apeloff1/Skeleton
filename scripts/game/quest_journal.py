"""Offline quest transaction runner: python -m scripts.game.quest_journal."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from skeleton.game.gameplay.quest_session import (
    GameplayContractError, QuestEngine, QuestPlan, QuestTrigger,
)

MAX_FILE = 1_048_576


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise GameplayContractError("duplicate JSON object key")
        value[key] = item
    return value


def _read(path: Path) -> object:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise GameplayContractError("input must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise GameplayContractError("input exceeds file budget")
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(GameplayContractError("non-finite JSON")),
        )
    finally:
        os.close(fd)


def _write_new(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    if len(raw) > MAX_FILE:
        raise GameplayContractError("save exceeds file budget")
    # mkstemp creates a private regular file in the same directory. link() is
    # atomic no-clobber publication; no pre-check/replace race is possible.
    fd, tmp = tempfile.mkstemp(prefix=".quest-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(tmp)


def _events(path: Path) -> list[QuestTrigger]:
    raw = _read(path)
    if not isinstance(raw, list):
        raise GameplayContractError("event file must contain a list")
    events = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {
            "sequence", "quest_id", "event_type", "source_id", "payload_digest",
        }:
            raise GameplayContractError("invalid event input")
        events.append(QuestTrigger(**entry))
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic offline quest journal")
    parser.add_argument("command", choices=("inspect", "run", "verify"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--events", type=Path, help="ordered authored event triggers for run")
    parser.add_argument("--save", type=Path, help="new no-clobber save output for run, or input for verify")
    args = parser.parse_args(argv)
    try:
        plan = QuestPlan.from_record(_read(args.plan))
        engine = QuestEngine(plan)
        if args.command == "inspect":
            if args.events or args.save:
                raise GameplayContractError("inspect does not accept events or save")
            result = {"world_id": plan.world_id, "plan_digest": plan.digest, "quest_order": plan.order}
        elif args.command == "run":
            if args.events is None or args.save is None:
                raise GameplayContractError("run requires --events and --save")
            session = engine.replay(_events(args.events))
            _write_new(args.save, session.save_record())
            result = {"state": session.as_state(), "state_digest": session.state_digest, "save_digest": session.save_metadata.digest}
        else:
            if args.save is None or args.events is not None:
                raise GameplayContractError("verify requires --save and forbids --events")
            session = engine.restore(_read(args.save))
            result = {"state": session.as_state(), "state_digest": session.state_digest, "save_digest": session.save_metadata.digest}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GameplayContractError, ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
        print("quest journal rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
