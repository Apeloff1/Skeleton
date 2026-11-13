"""Offline championship CLI with portable CAS saves and source-bound exports."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode
from .harbor_crafting_salvage_season import (
    MAX_SEASON_BOARD_BYTES, MAX_SEASON_SAVE_BYTES,
    append_salvage_round, compare_salvage_seasons, fast_forward_salvage_season,
    salvage_season_at, start_salvage_season, verify_salvage_season,
)
from .harbor_crafting_salvage_season_authoring import (
    MAX_REVISION_BYTES, edit_season, verify_season_revision,
)
from .harbor_crafting_salvage_season_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_season_package,
    play_season_package, verify_season_package, verify_season_package_play,
)
from .harbor_crafting_salvage_season_leaderboard import (
    MAX_BYTES as MAX_LEADERBOARD_BYTES, build_season_leaderboard,
    verify_season_leaderboard,
)
from .harbor_crafting_salvage_season_acceptance import (
    MAX_BYTES as MAX_ACCEPTANCE_BYTES, accept_salvage_season,
    verify_salvage_season_acceptance,
)
from .harbor_crafting_salvage_season_ui import play_season_live

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_SOURCE = FIXTURES / "harbor_lantern_quay.json"
DEFAULT_BOARD = FIXTURES / "harbor_lantern_quay_salvage_season.json"
COMMANDS = (
    "start", "next", "verify", "at", "compare", "fast-forward", "live",
    "author", "verify-author", "package", "verify-package", "play",
    "verify-play", "leaderboard", "verify-leaderboard", "accept", "verify-accept",
)


def _read(path: str | None, limit: int):
    if not path:
        raise HarborError("required season input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(limit + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(limit + 1)
    except OSError as exc:
        raise HarborError("cannot read requested season input") from exc
    return decode(raw, limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play and replay-verify original salvage championship")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--save")
    parser.add_argument("--other-save")
    parser.add_argument("--actions")
    parser.add_argument("--rounds")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--entries")
    parser.add_argument("--leaderboard")
    parser.add_argument("--acceptance")
    parser.add_argument("--preview-rounds")
    parser.add_argument("--expected-tip")
    parser.add_argument("--expected-board-digest")
    parser.add_argument("--index", type=int)
    parser.add_argument("--id", default="lantern_quay_salvage_season")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        cmd = args.command
        if cmd == "verify":
            result = verify_salvage_season(_read(args.save, MAX_SEASON_SAVE_BYTES),
                                            require_complete=args.require_complete)
        elif cmd == "next":
            result = append_salvage_round(
                _read(args.save, MAX_SEASON_SAVE_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_tip=args.expected_tip or "",
            )
        elif cmd == "at":
            result = salvage_season_at(_read(args.save, MAX_SEASON_SAVE_BYTES), args.index)
        elif cmd in {"compare", "fast-forward"}:
            left = _read(args.save, MAX_SEASON_SAVE_BYTES)
            right = _read(args.other_save, MAX_SEASON_SAVE_BYTES)
            result = (compare_salvage_seasons(left, right) if cmd == "compare"
                      else fast_forward_salvage_season(left, right))
        elif cmd == "verify-author":
            result = verify_season_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif cmd == "verify-package":
            result = verify_season_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif cmd == "play":
            result = play_season_package(
                _read(args.package, MAX_PACKAGE_BYTES),
                _read(args.rounds, MAX_BUNDLE_BYTES),
                require_complete=args.require_complete,
            )
        elif cmd == "verify-play":
            result = verify_season_package_play(_read(args.play, MAX_PLAY_BYTES),
                                                 require_complete=args.require_complete)
        elif cmd == "leaderboard":
            result = build_season_leaderboard(_read(args.entries, MAX_LEADERBOARD_BYTES))
        elif cmd == "verify-leaderboard":
            result = verify_season_leaderboard(_read(args.leaderboard, MAX_LEADERBOARD_BYTES))
        elif cmd == "verify-accept":
            result = verify_salvage_season_acceptance(_read(args.acceptance, MAX_ACCEPTANCE_BYTES))
        else:
            source = _read(args.source, MAX_BUNDLE_BYTES)
            board = _read(args.board, MAX_SEASON_BOARD_BYTES)
            if cmd == "start":
                result = start_salvage_season(source, board)
            elif cmd == "live":
                result = play_season_live(source, board)
            elif cmd == "author":
                result = edit_season(
                    source, board, _read(args.edits, MAX_SEASON_BOARD_BYTES),
                    expected_board_digest=args.expected_board_digest or "",
                    preview_round_actions=None if not args.preview_rounds
                    else _read(args.preview_rounds, MAX_BUNDLE_BYTES),
                )
            elif cmd == "package":
                result = build_season_package(source, board, package_id=args.id)
            elif cmd == "accept":
                result = accept_salvage_season(source, board, _read(args.rounds, MAX_BUNDLE_BYTES))
            else:
                raise HarborError("unsupported season command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, TypeError, KeyError) as exc:
        print("salvage season rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
