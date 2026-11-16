"""Installed offline expedition composition, gameplay, restart and evidence CLI."""
from __future__ import annotations

import argparse
import sys
from typing import BinaryIO, Sequence, TextIO

from skeleton.app.gameforge_expedition import (
    build_expedition, play_expedition, resume_expedition, verify_expedition,
)
from skeleton.app.gameforge_expedition_board import (
    episode_evidence, expedition_board, turn, verify_board, verify_evidence,
)
from skeleton.app.original_quest_cli import _encode, _object, _require, read_document
from skeleton.gameforge.errors import GameForgeError


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay source-bound campaign and local crafting gameplay")
    parser.add_argument("command", choices=("build", "play", "resume", "verify", "verify-play",
                                         "board", "turn", "verify-board", "evidence", "verify-evidence"))
    args = parser.parse_args(argv)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        cmd = args.command
        if cmd == "build":
            result = build_expedition(value)
        elif cmd == "play":
            data = _object(value, {"request", "actions"})
            result = play_expedition(data["request"], data["actions"])
        else:
            fields = {"request", "receipt"}
            extras = {"resume": {"additional"}, "turn": {"board_digest", "index"},
                      "evidence": {"objective"}, "verify-evidence": {"evidence"},
                      "verify-board": {"board"}}
            data = _object(value, fields | extras.get(cmd, set()))
            source, receipt = data["request"], data["receipt"]
            if cmd == "resume":
                result = resume_expedition(source, receipt, data["additional"])
            elif cmd == "board":
                result = expedition_board(source, receipt)
            elif cmd == "turn":
                result = turn(source, receipt, data["board_digest"], data["index"])
            elif cmd == "evidence":
                result = episode_evidence(source, receipt, data["objective"])
            else:
                if cmd == "verify-evidence":
                    ok = verify_evidence(source, receipt, data["evidence"])
                elif cmd == "verify-board":
                    ok = verify_board(source, receipt, data["board"])
                else:
                    ok = verify_expedition(source, receipt, session=cmd == "verify-play")
                _require(ok, "independent expedition replay mismatch")
                result = {"verified": True, "native_qualified": False, "release_qualified": False}
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError, OSError) as exc:
        errors.write("expedition rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
