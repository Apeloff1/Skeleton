"""Playable original salvage quest director CLI with authoring and export."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode
from .harbor_crafting_salvage import MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_salvage
from .harbor_crafting_salvage_quest_events import (
    MAX_BOARD_BYTES as MAX_STORY_BOARD_BYTES, MAX_STORY_REPORT_BYTES,
    build_salvage_story, resume_salvage_story, verify_salvage_story,
)
from .harbor_crafting_salvage_story_authoring import (
    MAX_BYTES as MAX_REVISION_BYTES, edit_salvage_story, verify_salvage_story_revision,
)
from .harbor_crafting_salvage_story_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_story_package,
    play_story_package, verify_story_package, verify_story_package_play,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_SOURCE = FIXTURES / "harbor_lantern_quay.json"
DEFAULT_SALVAGE = FIXTURES / "harbor_lantern_quay_salvage.json"
DEFAULT_STORY = FIXTURES / "harbor_lantern_quay_salvage_story.json"
COMMANDS = ("run", "verify", "resume", "author", "verify-author",
            "package", "verify-package", "play", "verify-play")


def _read(path: str | None, maximum: int):
    if not path:
        raise HarborError("required salvage story input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(maximum + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested salvage story input") from exc
    return decode(raw, maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, edit and verify original salvage story quests")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--salvage-board", default=str(DEFAULT_SALVAGE))
    parser.add_argument("--story-board", default=str(DEFAULT_STORY))
    parser.add_argument("--actions")
    parser.add_argument("--report")
    parser.add_argument("--story")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--expected-digest")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--id", default="lantern_quay_salvage_story")
    args = parser.parse_args(argv)
    try:
        cmd = args.command
        if cmd == "verify":
            result = verify_salvage_story(_read(args.story, MAX_STORY_REPORT_BYTES),
                                           require_all=args.require_all)
        elif cmd == "resume":
            result = resume_salvage_story(
                _read(args.story, MAX_STORY_REPORT_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                expected_digest=args.expected_digest or "", require_all=args.require_all,
            )
        elif cmd == "verify-author":
            result = verify_salvage_story_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif cmd == "verify-package":
            result = verify_story_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif cmd == "play":
            result = play_story_package(
                _read(args.package, MAX_PACKAGE_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES), require_all=args.require_all,
            )
        elif cmd == "verify-play":
            result = verify_story_package_play(_read(args.play, MAX_PLAY_BYTES),
                                                require_all=args.require_all)
        else:
            source = _read(args.source, MAX_BUNDLE_BYTES)
            salvage_board = _read(args.salvage_board, MAX_BOARD_BYTES)
            story_board = _read(args.story_board, MAX_STORY_BOARD_BYTES)
            if cmd == "package":
                result = build_story_package(source, salvage_board, story_board,
                                             package_id=args.id)
            else:
                report = (_read(args.report, MAX_REPORT_BYTES) if args.report
                          else build_salvage(source, salvage_board,
                                             _read(args.actions, MAX_BUNDLE_BYTES)
                                             if cmd == "run" else []))
                if cmd == "run":
                    result = build_salvage_story(report, story_board, require_all=args.require_all)
                elif cmd == "author":
                    result = edit_salvage_story(
                        report, story_board, _read(args.edits, MAX_STORY_BOARD_BYTES),
                        expected_board_digest=args.expected_digest or "",
                        preview=args.preview,
                    )
                else:
                    raise HarborError("unsupported salvage story command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, TypeError, KeyError) as exc:
        print("salvage story rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
