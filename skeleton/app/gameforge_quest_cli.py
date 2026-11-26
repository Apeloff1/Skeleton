"""Offline GameForge quest composition, play and checkpoint replay CLI."""
from __future__ import annotations

import argparse
import sys
from typing import BinaryIO, Sequence, TextIO

from skeleton.app.gameforge_quest_bridge import (
    build_design, play, resume, verify_design, verify_session,
)
from skeleton.app.original_quest_cli import _encode, _object, _require, read_document
from skeleton.gameforge.errors import GameForgeError


def main(
    argv: Sequence[str] | None = None, *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Compose a deterministic GameForge quest and replay legal abstract player events."
    )
    parser.add_argument("command", choices=("build", "verify", "play", "verify-play", "resume"))
    args = parser.parse_args(argv)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        if args.command == "build":
            result = build_design(value)
        elif args.command == "play":
            bundle = _object(value, {"request", "actions"})
            result = play(bundle["request"], bundle["actions"])
        elif args.command == "resume":
            bundle = _object(value, {"request", "receipt", "additional"})
            result = resume(bundle["request"], bundle["receipt"], bundle["additional"])
        else:
            bundle = _object(value, {"request", "receipt"})
            verification = verify_design if args.command == "verify" else verify_session
            _require(verification(bundle["request"], bundle["receipt"]),
                     "receipt differs from independently supplied source replay")
            result = {
                "verified": True,
                "scope": "abstract_design" if args.command == "verify" else "abstract_player_session",
                "native_qualified": False,
                "release_qualified": False,
            }
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError, OSError) as exc:
        errors.write("gameforge quest rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
