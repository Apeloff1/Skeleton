"""Offline beacon rescue CLI: authored source -> play -> save -> replay -> export."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode
from .harbor_crafting_beacons import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_beacon_rescue,
    resume_beacon_rescue, verify_beacon_rescue,
)
from .harbor_crafting_beacon_authoring import (
    MAX_REVISION_BYTES, edit_beacons, verify_beacon_revision,
)
from .harbor_crafting_beacon_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_beacon_package,
    play_beacon_package, verify_beacon_package, verify_beacon_package_play,
    resume_beacon_package,
)

from .harbor_crafting_beacon_ui import play_beacon_live
from .harbor_crafting_beacon_guidance import legal_beacon_actions, verify_beacon_guidance
from .harbor_crafting_beacon_tides import (
    MAX_BOARD_BYTES as MAX_TIDE_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_TIDE_REPORT_BYTES,
    build_beacon_tide_report, verify_beacon_tide_report, resume_beacon_tide_report,
)
from .harbor_crafting_beacon_tide_authoring import (
    MAX_REVISION_BYTES as MAX_TIDE_REVISION_BYTES,
    edit_beacon_tides, verify_beacon_tide_revision,
)
from .harbor_crafting_beacon_quests import (
    MAX_BOARD_BYTES as MAX_QUEST_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_QUEST_REPORT_BYTES,
    build_beacon_quest_report, verify_beacon_quest_report,
)
from .harbor_crafting_beacon_quest_authoring import (
    MAX_REVISION_BYTES as MAX_QUEST_REVISION_BYTES,
    edit_beacon_quests, verify_beacon_quest_revision,
)
from .harbor_crafting_beacon_journal import (
    MAX_JOURNAL_BYTES, create_beacon_journal, append_beacon_journal,
    verify_beacon_journal, beacon_journal_at, fork_beacon_journal,
)
from .harbor_crafting_beacon_acceptance import (
    MAX_ACCEPTANCE_BYTES, accept_beacon_play, verify_beacon_acceptance,
)

COMMANDS = (
    "run", "verify", "resume", "status", "live", "hint", "verify-hint",
    "accept", "verify-accept", "author",
    "journal-init", "journal-append", "journal-verify", "journal-at", "journal-fork",
    "quest-run", "quest-verify", "quest-author", "quest-verify-author",
    "tide-run", "tide-verify", "tide-resume", "tide-author", "tide-verify-author", "verify-author",
    "package", "verify-package", "play", "verify-play", "resume-play",
)


def _read(path: str | None, maximum: int):
    if not path:
        raise HarborError("required input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(maximum + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested input") from exc
    return decode(raw, maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play and replay-verify original beacon rescue")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source")
    parser.add_argument("--board")
    parser.add_argument("--actions")
    parser.add_argument("--report")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--guidance")
    parser.add_argument("--acceptance")
    parser.add_argument("--journal")
    parser.add_argument("--tide-board")
    parser.add_argument("--tide-report")
    parser.add_argument("--tide-revision")
    parser.add_argument("--quest-board")
    parser.add_argument("--quest-report")
    parser.add_argument("--quest-revision")
    parser.add_argument("--index", type=int)
    parser.add_argument("--id", default="lantern-quay-beacons")
    parser.add_argument("--expected-digest")
    parser.add_argument("--require-rescue", action="store_true")
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command == "tide-run":
            result = build_beacon_tide_report(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
                _read(args.tide_board, MAX_TIDE_BOARD_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                require_rescue=args.require_rescue,
            )
        elif command == "tide-verify":
            result = verify_beacon_tide_report(
                _read(args.tide_report, MAX_TIDE_REPORT_BYTES),
                require_rescue=args.require_rescue,
            )
        elif command == "tide-resume":
            result = resume_beacon_tide_report(
                _read(args.tide_report, MAX_TIDE_REPORT_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_digest=args.expected_digest or "",
                require_rescue=args.require_rescue,
            )
        elif command == "tide-author":
            result = edit_beacon_tides(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
                _read(args.tide_board, MAX_TIDE_BOARD_BYTES),
                _read(args.edits, MAX_TIDE_BOARD_BYTES),
                expected_board_digest=args.expected_digest or "",
                preview_report=None if not args.tide_report
                else _read(args.tide_report, MAX_TIDE_REPORT_BYTES),
            )
        elif command == "tide-verify-author":
            result = verify_beacon_tide_revision(
                _read(args.tide_revision, MAX_TIDE_REVISION_BYTES),
            )
        elif command == "quest-run":
            result = build_beacon_quest_report(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.quest_board, MAX_QUEST_BOARD_BYTES),
                require_complete=args.require_rescue,
            )
        elif command == "quest-verify":
            result = verify_beacon_quest_report(
                _read(args.quest_report, MAX_QUEST_REPORT_BYTES),
                require_complete=args.require_rescue,
            )
        elif command == "quest-author":
            result = edit_beacon_quests(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.quest_board, MAX_QUEST_BOARD_BYTES),
                _read(args.edits, MAX_QUEST_BOARD_BYTES),
                expected_board_digest=args.expected_digest or "",
                preview_report=None if not args.quest_report
                else _read(args.quest_report, MAX_QUEST_REPORT_BYTES),
            )
        elif command == "quest-verify-author":
            result = verify_beacon_quest_revision(
                _read(args.quest_revision, MAX_QUEST_REVISION_BYTES),
            )
        elif command == "journal-init":
            result = create_beacon_journal(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
            )
        elif command == "journal-append":
            result = append_beacon_journal(
                _read(args.journal, MAX_JOURNAL_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_tip=args.expected_digest or "",
            )
        elif command == "journal-verify":
            result = verify_beacon_journal(_read(args.journal, MAX_JOURNAL_BYTES))
        elif command == "journal-at":
            result = beacon_journal_at(
                _read(args.journal, MAX_JOURNAL_BYTES), args.index,
            )
        elif command == "journal-fork":
            result = fork_beacon_journal(
                _read(args.journal, MAX_JOURNAL_BYTES), args.index,
            )
        elif command == "run":
            result = build_beacon_rescue(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                require_rescue=args.require_rescue,
            )
        elif command == "live":
            result = play_beacon_live(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
                instream=sys.stdin, outstream=sys.stderr,
                initial_report=None if not args.report else _read(args.report, MAX_REPORT_BYTES),
            )
            if args.require_rescue:
                verify_beacon_rescue(result, require_rescue=True)
        elif command == "accept":
            result = accept_beacon_play(_read(args.play, MAX_PLAY_BYTES))
        elif command == "verify-accept":
            result = verify_beacon_acceptance(
                _read(args.play, MAX_PLAY_BYTES),
                _read(args.acceptance, MAX_ACCEPTANCE_BYTES),
            )
        elif command == "hint":
            result = legal_beacon_actions(_read(args.report, MAX_REPORT_BYTES))
        elif command == "verify-hint":
            result = verify_beacon_guidance(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.guidance, 65536),
            )
        elif command == "verify":
            result = verify_beacon_rescue(
                _read(args.report, MAX_REPORT_BYTES), require_rescue=args.require_rescue,
            )
        elif command == "status":
            report = _read(args.report, MAX_REPORT_BYTES)
            result = verify_beacon_rescue(report)
        elif command == "resume":
            result = resume_beacon_rescue(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_digest=args.expected_digest or "",
                require_rescue=args.require_rescue,
            )
        elif command == "author":
            result = edit_beacons(
                _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
                _read(args.edits, MAX_BOARD_BYTES),
                expected_board_digest=args.expected_digest or "",
                preview_report=None if not args.report else _read(args.report, MAX_REPORT_BYTES),
            )
        elif command == "verify-author":
            result = verify_beacon_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif command == "package":
            result = build_beacon_package(
                args.id, _read(args.source, MAX_BUNDLE_BYTES),
                _read(args.board, MAX_BOARD_BYTES),
            )
        elif command == "verify-package":
            result = verify_beacon_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif command == "play":
            result = play_beacon_package(
                _read(args.package, MAX_PACKAGE_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                require_rescue=args.require_rescue,
            )
        elif command == "verify-play":
            result = verify_beacon_package_play(
                _read(args.play, MAX_PLAY_BYTES), require_rescue=args.require_rescue,
            )
        else:
            result = resume_beacon_package(
                _read(args.play, MAX_PLAY_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_digest=args.expected_digest or "",
                require_rescue=args.require_rescue,
            )
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except HarborError as exc:
        print("Beacon rescue rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
