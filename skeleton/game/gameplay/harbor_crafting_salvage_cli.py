"""Public CLI for playable salvage, editing, journal custody and portable export."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, canonical, decode, digest
from .harbor_crafting_salvage import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_salvage, resume_salvage,
    verify_salvage,
)
from .harbor_crafting_salvage_authoring import (
    MAX_REVISION_BYTES, edit_salvage, verify_salvage_revision,
)
from .harbor_crafting_salvage_journal import (
    MAX_JOURNAL_BYTES, append_salvage_journal, create_salvage_journal,
    fork_salvage_journal, salvage_journal_at, verify_salvage_journal,
)
from .harbor_crafting_salvage_package import (
    MAX_PACKAGE_BYTES, MAX_PLAY_BYTES, build_salvage_package,
    play_salvage_package, verify_salvage_package, verify_salvage_package_play,
)
from .harbor_crafting_salvage_acceptance import (
    MAX_BYTES as MAX_ACCEPTANCE_BYTES, accept_salvage, verify_salvage_acceptance,
)
from .harbor_crafting_salvage_ui import play_salvage_live
from .harbor_crafting_salvage_guidance import (
    MAX_BYTES as MAX_GUIDANCE_BYTES, build_salvage_guidance, verify_salvage_guidance,
)
from .harbor_crafting_salvage_contracts import (
    MAX_CONTRACT_BOARD_BYTES, MAX_CONTRACT_REPORT_BYTES,
    build_salvage_contract_report, verify_salvage_contract_report,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_SOURCE = FIXTURES / "harbor_lantern_quay.json"
DEFAULT_BOARD = FIXTURES / "harbor_lantern_quay_salvage.json"
COMMANDS = (
    "run", "verify", "resume", "status", "live", "author", "verify-author",
    "journal-init", "journal-append", "journal-verify", "journal-at", "journal-fork",
    "package", "verify-package", "play", "verify-play", "accept", "verify-accept",
    "hint", "verify-hint", "contract-run", "contract-verify",
)


def _read(path: str | None, limit: int):
    if not path:
        raise HarborError("required input path missing")
    try:
        if path == "-":
            raw = sys.stdin.buffer.read(limit + 1)
        else:
            with Path(path).open("rb") as stream:
                raw = stream.read(limit + 1)
    except OSError as exc:
        raise HarborError("cannot read requested salvage input") from exc
    return decode(raw, limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, edit and replay-verify Lantern Quay salvage")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--actions")
    parser.add_argument("--report")
    parser.add_argument("--edits")
    parser.add_argument("--revision")
    parser.add_argument("--journal")
    parser.add_argument("--package")
    parser.add_argument("--play")
    parser.add_argument("--acceptance")
    parser.add_argument("--guidance")
    parser.add_argument("--contract-board", default=str(FIXTURES / "harbor_lantern_quay_salvage_contracts.json"))
    parser.add_argument("--contract-report")
    parser.add_argument("--horizon", type=int, default=16)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--expected-digest")
    parser.add_argument("--index", type=int)
    parser.add_argument("--id", default="lantern_quay_salvage")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command in {"verify", "resume", "status"}:
            report = _read(args.report, MAX_REPORT_BYTES)
            if command == "resume":
                result = resume_salvage(report, _read(args.actions, MAX_BUNDLE_BYTES),
                                        expected_digest=args.expected_digest or "",
                                        require_complete=args.require_complete)
            else:
                result = verify_salvage(report, require_complete=args.require_complete)
        elif command == "verify-hint":
            result = verify_salvage_guidance(_read(args.guidance, MAX_GUIDANCE_BYTES))
        elif command == "hint":
            result = build_salvage_guidance(_read(args.report, MAX_REPORT_BYTES),
                                             horizon=args.horizon)
        elif command == "contract-run":
            result = build_salvage_contract_report(
                _read(args.report, MAX_REPORT_BYTES),
                _read(args.contract_board, MAX_CONTRACT_BOARD_BYTES),
                require_all=args.require_all,
            )
        elif command == "contract-verify":
            result = verify_salvage_contract_report(
                _read(args.contract_report, MAX_CONTRACT_REPORT_BYTES),
                require_all=args.require_all,
            )
        elif command == "verify-author":
            result = verify_salvage_revision(_read(args.revision, MAX_REVISION_BYTES))
        elif command == "verify-play":
            result = verify_salvage_package_play(_read(args.play, MAX_PLAY_BYTES),
                                                  require_complete=args.require_complete)
        elif command == "verify-package":
            result = verify_salvage_package(_read(args.package, MAX_PACKAGE_BYTES))
        elif command == "verify-accept":
            result = verify_salvage_acceptance(_read(args.acceptance, MAX_ACCEPTANCE_BYTES))
        elif command in {"journal-verify", "journal-at", "journal-fork", "journal-append"}:
            journal = _read(args.journal, MAX_JOURNAL_BYTES)
            if command == "journal-verify":
                checked = verify_salvage_journal(journal)
                result = {"tip": checked["tip"], "revision_count": checked["revision_count"]}
            elif command == "journal-at":
                result = salvage_journal_at(journal, args.index)
            elif command == "journal-fork":
                result = fork_salvage_journal(journal, args.index)
            else:
                result = append_salvage_journal(
                    journal, _read(args.actions, MAX_BUNDLE_BYTES),
                    expected_tip=args.expected_digest or "",
                )
        elif command == "play":
            result = play_salvage_package(
                _read(args.package, MAX_PACKAGE_BYTES),
                _read(args.actions, MAX_BUNDLE_BYTES),
                require_complete=args.require_complete,
            )
        else:
            source = _read(args.source, MAX_BUNDLE_BYTES)
            board = _read(args.board, MAX_BOARD_BYTES)
            if command == "run":
                result = build_salvage(source, board, _read(args.actions, MAX_BUNDLE_BYTES),
                                       require_complete=args.require_complete)
            elif command == "live":
                result = play_salvage_live(source, board)
                if args.require_complete:
                    verify_salvage(result, require_complete=True)
            elif command == "author":
                result = edit_salvage(source, board, _read(args.edits, MAX_BOARD_BYTES),
                                      expected_board_digest=args.expected_digest or "")
            elif command == "journal-init":
                result = create_salvage_journal(source, board)
            elif command == "package":
                result = build_salvage_package(source, board, package_id=args.id)
            elif command == "accept":
                result = accept_salvage(source, board, _read(args.actions, MAX_BUNDLE_BYTES))
            else:
                raise HarborError("unsupported salvage command")
        sys.stdout.buffer.write(canonical(result) + b"\n")
        return 0
    except (HarborError, TypeError, KeyError) as exc:
        print("salvage rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
