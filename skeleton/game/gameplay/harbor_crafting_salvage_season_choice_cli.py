"""Playable offline choice consequences after replay-earned salvage championship."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, canonical, decode
from .harbor_crafting_salvage_season import MAX_SEASON_SAVE_BYTES
from .harbor_crafting_salvage_season_choices import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_season_choice,
    compare_season_choices, verify_season_choice,
)
from .harbor_crafting_salvage_season_choice_authoring import (
    MAX_REVISION_BYTES, edit_season_choices, verify_season_choice_revision,
)
from .harbor_crafting_salvage_season_choice_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_choice_package,
    play_choice_package, verify_choice_package, verify_choice_package_play,
)

DEFAULT_BOARD = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay_salvage_season_choices.json"
COMMANDS = ("choose", "verify", "compare", "author", "verify-author",
            "package", "verify-package", "play", "verify-play")


def _read(path: str | None, limit: int):
    if not path:
        raise HarborError("required salvage choice input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(limit + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(limit + 1)
    except OSError as exc:
        raise HarborError("cannot read requested salvage choice input") from exc
    return decode(raw, limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Earned salvage epilogues and portable replay")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--save")
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--choice", default="rebuild_quay")
    parser.add_argument("--report")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--expected-board-digest")
    parser.add_argument("--preview-choice")
    parser.add_argument("--id", default="lantern_quay_salvage_epilogues")
    args = parser.parse_args(argv)
    try:
        cmd = args.command
        if cmd == "verify":
            result = verify_season_choice(_read(args.report, MAX_REPORT_BYTES))
        elif cmd == "verify-author":
            result = verify_season_choice_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif cmd == "verify-package":
            result = verify_choice_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif cmd == "play":
            result = play_choice_package(_read(args.package, MAX_PACKAGE_BYTES), args.choice)
        elif cmd == "verify-play":
            result = verify_choice_package_play(_read(args.play, MAX_PLAY_BYTES))
        else:
            save = _read(args.save, MAX_SEASON_SAVE_BYTES)
            board = _read(args.board, MAX_BOARD_BYTES)
            if cmd == "choose":
                result = build_season_choice(save, board, args.choice)
            elif cmd == "compare":
                result = compare_season_choices(save, board)
            elif cmd == "author":
                result = edit_season_choices(
                    save, board, _read(args.edits, MAX_BOARD_BYTES),
                    expected_board_digest=args.expected_board_digest or "",
                    preview_choice=args.preview_choice,
                )
            elif cmd == "package":
                result = build_choice_package(save, board, package_id=args.id)
            else:
                raise HarborError("unsupported salvage choice command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, TypeError, KeyError) as exc:
        print("salvage choice rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
