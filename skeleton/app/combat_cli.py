"""Bounded offline combat session CLI, delegated by the assembled application."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence

from skeleton.game.gameplay.encounter_session import (
    CombatSessionError, advance, replay, verify_save,
)

MAX_INPUT_BYTES = 96 * 1024
MAX_OUTPUT_BYTES = 96 * 1024


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise CombatSessionError("duplicate JSON property")
        out[key] = value
    return out


def _nonfinite(_: str) -> None:
    raise CombatSessionError("nonfinite JSON values are forbidden")


def _read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise CombatSessionError("input must be a regular local file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise CombatSessionError("input file exceeds local budget")
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise CombatSessionError("input file exceeds local budget")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CombatSessionError("invalid JSON file") from exc
    if not isinstance(value, dict):
        raise CombatSessionError("JSON input must be an object")
    return value


def _write(path: Path, value: dict) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
           + "\n").encode("ascii")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise CombatSessionError("combat save exceeds output budget")
    target = path.expanduser().absolute()
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise CombatSessionError("output must be a new file in an existing directory")
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
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app combat-session",
        description="Play or verify an original deterministic offline combat encounter.",
    )
    parser.add_argument("--source", type=Path, required=True,
                        help="reviewed original combat encounter JSON")
    parser.add_argument("--save", type=Path, help="existing save to verify/resume")
    parser.add_argument("--command", help='one JSON action, e.g. {"action":"attack","attack_id":"jab"}')
    parser.add_argument("--output", type=Path, help="exclusive new path for next save")
    parser.add_argument("--verify", action="store_true", help="verify existing save without acting")
    args = parser.parse_args(argv)
    if args.verify and (args.command is not None or args.output is not None):
        parser.error("--verify is read-only and cannot accept command/output")
    if args.verify and args.save is None:
        parser.error("--verify requires --save")
    if (args.command is None) != (args.output is None):
        parser.error("--command and --output must be provided together")
    try:
        source = _read(args.source)
        saved = _read(args.save) if args.save is not None else None
        if args.verify:
            result = verify_save(source, saved)
        elif args.command is not None:
            command = json.loads(args.command, object_pairs_hook=_pairs,
                                 parse_constant=_nonfinite)
            if not isinstance(command, dict):
                raise CombatSessionError("command must be an object")
            result = advance(source, saved, command)
            _write(args.output, result)
        else:
            result = replay(source, []) if saved is None else verify_save(source, saved)
        print(json.dumps({"ok": True, "phase": result["state"]["phase"],
                          "turn": result["state"]["turn"],
                          "state": result["state"],
                          "source_digest": result["source_digest"],
                          "state_digest": result["state_digest"],
                          "event_digest": result["event_digest"],
                          "save_metadata_digest": result["save_metadata_digest"],
                          "verified": True, "native_qualified": False,
                          "release_qualified": False}, sort_keys=True))
        return 0
    except (CombatSessionError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print("combat session rejected: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
