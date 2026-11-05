"""Offline authored dialogue choices, quest consequences and verified saves."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence
from skeleton.game.gameplay.dialogue_session import (
    DialogueSessionError, choose, replay, verify_save,
)

def _pairs(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise DialogueSessionError("duplicate JSON property")
        result[key] = value
    return result

def _bad_number(_: str) -> None:
    raise DialogueSessionError("nonfinite JSON number")

def _read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise DialogueSessionError("dialogue input must be a regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 96 * 1024:
            raise DialogueSessionError("dialogue input too large")
        raw = stream.read(96 * 1024 + 1)
    if len(raw) > 96 * 1024:
        raise DialogueSessionError("dialogue input too large")
    try:
        result = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=_pairs, parse_constant=_bad_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DialogueSessionError("invalid dialogue JSON") from exc
    if not isinstance(result, dict):
        raise DialogueSessionError("dialogue JSON must be an object")
    return result

def _write(path: Path, value: dict) -> None:
    raw = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > 96 * 1024:
        raise DialogueSessionError("dialogue save too large")
    target = path.expanduser().absolute()
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise DialogueSessionError("dialogue output must be a new local file")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton.app.dialogue_cli",
                                     description="Play an original source-bound offline dialogue.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--choice", help="authored choice ID")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify and (args.save is None or args.choice or args.output):
        parser.error("--verify requires --save and forbids changes")
    if (args.choice is None) != (args.output is None):
        parser.error("--choice requires --output, and vice versa")
    try:
        source = _read(args.source)
        previous = _read(args.save) if args.save else None
        if args.verify:
            result = verify_save(source, previous)
        elif args.choice is not None:
            result = choose(source, previous, args.choice)
            _write(args.output, result)
        else:
            result = replay(source, []) if previous is None else verify_save(source, previous)
        print(json.dumps({"ok": True, "state": result["state"],
                          "source_digest": result["source_digest"],
                          "state_digest": result["state_digest"],
                          "event_digest": result["event_digest"],
                          "verified": True, "native_qualified": False,
                          "release_qualified": False}, sort_keys=True))
        return 0
    except (DialogueSessionError, OSError, ValueError, TypeError) as exc:
        print("dialogue session rejected: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
