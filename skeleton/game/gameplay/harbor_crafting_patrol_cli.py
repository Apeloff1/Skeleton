"""User-reachable patrol gameplay, source editor and portable JSON CLI."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode, digest
from .harbor_crafting_patrol import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_patrol, resume_patrol, verify_patrol,
)
from .harbor_crafting_patrol_authoring import (
    MAX_REVISION_BYTES, edit_patrol_board, verify_patrol_revision,
)
from .harbor_crafting_patrol_ui import play_live
from .harbor_crafting_patrol_guidance import patrol_hints
from .harbor_crafting_patrol_quest_authoring import (
    MAX_REVISION_BYTES as MAX_QUEST_REVISION_BYTES,
    edit_patrol_quests, verify_patrol_quest_revision,
)
from .harbor_crafting_patrol_quests import (
    MAX_BOARD_BYTES as MAX_QUEST_BOARD_BYTES,
    MAX_LEDGER_BYTES, build_patrol_quests, verify_patrol_quests,
)
from .harbor_crafting_patrol_debrief import (
    MAX_BOARD_BYTES as MAX_DEBRIEF_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_DEBRIEF_REPORT_BYTES,
    build_patrol_debrief, compare_patrol_debriefs, verify_patrol_debrief,
)
from .harbor_crafting_patrol_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_patrol_package,
    play_patrol_package, verify_patrol_package, verify_patrol_package_play,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_SOURCE = FIXTURES / "harbor_lantern_quay.json"
DEFAULT_BOARD = FIXTURES / "harbor_lantern_quay_patrol.json"
DEFAULT_DEBRIEF = FIXTURES / "harbor_lantern_quay_patrol_debrief.json"
DEFAULT_QUEST_BOARD = FIXTURES / "harbor_lantern_quay_patrol_quests.json"
COMMANDS = ("quest-author", "quest-verify-author", "quest-run", "quest-verify", "hint", "choices", "debrief", "verify-debrief", "live", "run", "verify", "resume", "author", "verify-author",
            "package", "verify-package", "play", "verify-play")


def _read(path: str | None, maximum: int):
    if not path:
        raise HarborError("required patrol input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(maximum + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested patrol input") from exc
    return decode(raw, maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play and author original stealth patrol")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--actions")
    parser.add_argument("--report")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--debrief", default=str(DEFAULT_DEBRIEF))
    parser.add_argument("--choice", default="publish")
    parser.add_argument("--quest-board", default=str(DEFAULT_QUEST_BOARD))
    parser.add_argument("--quest-ledger")
    parser.add_argument("--quest-edits")
    parser.add_argument("--quest-revision")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--expected-digest")
    parser.add_argument("--preview-actions")
    parser.add_argument("--id", default="lantern_quay_patrol")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command == "quest-author":
            result = edit_patrol_quests(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.quest_board, MAX_QUEST_BOARD_BYTES),
                _read(args.quest_edits, MAX_QUEST_BOARD_BYTES),
                expected_digest=args.expected_digest or "",
            )
        elif command == "quest-verify-author":
            result = verify_patrol_quest_revision(
                _read(args.quest_revision, MAX_QUEST_REVISION_BYTES),
            )
        elif command == "quest-run":
            result = build_patrol_quests(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.quest_board, MAX_QUEST_BOARD_BYTES),
                require_all=args.require_all,
            )
        elif command == "quest-verify":
            result = verify_patrol_quests(
                _read(args.quest_ledger, MAX_LEDGER_BYTES),
                require_all=args.require_all,
            )
        elif command == "hint":
            result = patrol_hints(_read(args.report, MAX_REPORT_BYTES))
        elif command == "verify-debrief":
            result = verify_patrol_debrief(_read(args.debrief, MAX_DEBRIEF_REPORT_BYTES))
        elif command == "choices":
            result = compare_patrol_debriefs(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.debrief, MAX_DEBRIEF_BOARD_BYTES),
            )
        elif command == "debrief":
            result = build_patrol_debrief(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.debrief, MAX_DEBRIEF_BOARD_BYTES), args.choice,
            )
        elif command == "live":
            play_live(_read(args.source, MAX_BUNDLE_BYTES),
                      _read(args.board, MAX_BOARD_BYTES),
                      input_stream=sys.stdin, output_stream=sys.stdout,
                      require_complete=args.require_complete)
            return 0
        if command == "verify":
            result = verify_patrol(_read(args.report, MAX_REPORT_BYTES),
                                   require_complete=args.require_complete)
        elif command == "resume":
            result = resume_patrol(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_digest=args.expected_digest or "",
                require_complete=args.require_complete,
            )
        elif command == "verify-author":
            result = verify_patrol_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif command == "verify-package":
            result = verify_patrol_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif command == "play":
            result = play_patrol_package(
                _read(args.package, MAX_PACKAGE_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                require_complete=args.require_complete,
            )
        elif command == "verify-play":
            result = verify_patrol_package_play(
                _read(args.play, MAX_PLAY_BYTES),
                require_complete=args.require_complete,
            )
        else:
            source = _read(args.source, MAX_BUNDLE_BYTES)
            board = _read(args.board, MAX_BOARD_BYTES)
            if command == "run":
                result = build_patrol(source, board, _read(args.actions, MAX_BUNDLE_BYTES),
                                      require_complete=args.require_complete)
            elif command == "package":
                result = build_patrol_package(
                    source, board, _read(args.actions, MAX_BUNDLE_BYTES),
                    package_id=args.id,
                )
            elif command == "author":
                result = edit_patrol_board(
                    source, board, _read(args.edits, MAX_BOARD_BYTES),
                    expected_digest=args.expected_digest or "",
                    preview_actions=(_read(args.preview_actions, MAX_BUNDLE_BYTES)
                                     if args.preview_actions else None),
                )
            else:
                raise HarborError("unsupported patrol command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, KeyError, TypeError) as exc:
        print("patrol rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
