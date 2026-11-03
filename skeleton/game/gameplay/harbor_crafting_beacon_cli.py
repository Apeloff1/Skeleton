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

COMMANDS = (
    "run", "verify", "resume", "status", "live", "hint", "verify-hint", "author", "verify-author",
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
    parser.add_argument("--id", default="lantern-quay-beacons")
    parser.add_argument("--expected-digest")
    parser.add_argument("--require-rescue", action="store_true")
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command == "run":
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
