"""Command-line playable Lantern Quay campaign, checkpoint and replay verifier."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, canonical, decode, demo_actions,
    export_bundle, load_source, verify_bundle,
)
from .harbor_crafting_authoring import author_revision, verify_revision
from .harbor_crafting_planner import solve, verify_plan
from .harbor_crafting_missions import mission_report, verify_mission_report, solve_missions
from .harbor_crafting_mission_authoring import author_mission_revision, verify_mission_revision
from .harbor_crafting_mission_branches import mission_branch_report, verify_mission_branch_report
from .harbor_crafting_ui import play_live
from .harbor_crafting_sessions import (
    branch_portfolio, checkpoint, resume_bundle, verify_portfolio,
)

DEFAULT_WORLD = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay.json"
DEFAULT_MISSIONS = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay_missions.json"


def _read(path: str, maximum: int = MAX_BUNDLE_BYTES) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read(maximum + 1)
        with Path(path).open("rb") as stream:
            return stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested input") from exc


def _required_json(path: str | None, name: str):
    if not path:
        raise HarborError("--" + name + " is required")
    return decode(_read(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, export, branch and replay-verify Lantern Quay")
    parser.add_argument("command", choices=(
        "demo", "play", "verify", "checkpoint", "resume", "portfolio", "verify-portfolio", "author", "verify-author", "solve", "verify-plan", "play-live", "mission-report", "verify-mission-report", "solve-missions", "author-missions", "verify-mission-author", "mission-checkpoint", "mission-resume", "mission-portfolio", "verify-mission-portfolio"
    ))
    parser.add_argument("--source", default=str(DEFAULT_WORLD))
    parser.add_argument("--actions", help="JSON array file or '-' for stdin")
    parser.add_argument("--bundle", help="JSON bundle file or '-' for stdin")
    parser.add_argument("--branches", help="JSON map of branch names to action arrays")
    parser.add_argument("--expected-terminal-digest", help="CAS lease for resume")
    parser.add_argument("--tick", type=int, help="Historical checkpoint tick")
    parser.add_argument("--edits", help="JSON list of transactional source edits")
    parser.add_argument("--revision", help="JSON source revision for verification")
    parser.add_argument("--expected-source-digest", help="CAS lease for source editing")
    parser.add_argument("--choice", choices=("signal", "shelter"), default="signal")
    parser.add_argument("--plan", help="JSON solver plan for verification")
    parser.add_argument("--missions", default=str(DEFAULT_MISSIONS), help="Authored mission board JSON")
    parser.add_argument("--report", help="Portable mission report JSON for replay verification")
    parser.add_argument("--mission-edits", help="Transactional mission edit JSON")
    parser.add_argument("--expected-board-digest", help="Optimistic board revision lease")
    parser.add_argument("--mission-revision", help="Portable mission revision JSON")
    parser.add_argument("--preview-bundle", help="Optional canonical gameplay bundle for edited mission preview")
    parser.add_argument("--require-all", action="store_true", help="Require every authored mission to be earned")
    parser.add_argument("--require-win", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-mission-portfolio":
            output = {"verified": True, "branches": verify_mission_branch_report(
                _required_json(args.report, "report"))}
        elif args.command == "mission-portfolio":
            output = mission_branch_report(
                _required_json(args.bundle, "bundle"), decode(_read(args.missions)))
        elif args.command == "mission-checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for mission-checkpoint")
            output = mission_report(
                checkpoint(_required_json(args.bundle, "bundle"), args.tick),
                decode(_read(args.missions)), require_all=args.require_all)
        elif args.command == "mission-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for mission-resume")
            resumed = resume_bundle(
                _required_json(args.bundle, "bundle"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
            )
            output = mission_report(resumed, decode(_read(args.missions)), require_all=args.require_all)
        elif args.command == "verify-mission-author":
            output = {"verified": True, "board": verify_mission_revision(
                _required_json(args.mission_revision, "mission-revision"))}
        elif args.command == "author-missions":
            if not args.expected_board_digest:
                raise HarborError("--expected-board-digest is required for author-missions")
            output = author_mission_revision(
                decode(_read(args.missions)), load_source(Path(args.source)),
                _required_json(args.mission_edits, "mission-edits"),
                expected_board_digest=args.expected_board_digest,
                preview_bundle=_required_json(args.preview_bundle, "preview-bundle") if args.preview_bundle else None,
            )
        elif args.command == "verify-mission-report":
            result = verify_mission_report(_required_json(args.report, "report"), require_all=args.require_all)
            output = {"verified": True, **result}
        elif args.command == "mission-report":
            output = mission_report(
                _required_json(args.bundle, "bundle"), decode(_read(args.missions)),
                require_all=args.require_all,
            )
        elif args.command == "solve-missions":
            output = solve_missions(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice,
            )
        elif args.command == "play-live":
            return play_live(load_source(Path(args.source)), sys.stdin, sys.stdout)
        if args.command == "verify-plan":
            state = verify_plan(_required_json(args.plan, "plan"))
            output = {"verified": True, "state": state}
        elif args.command == "solve":
            output = solve(load_source(Path(args.source)), choice=args.choice)
        elif args.command == "verify-author":
            source = verify_revision(_required_json(args.revision, "revision"))
            output = {"verified": True, "source": source}
        elif args.command == "author":
            if not args.expected_source_digest:
                raise HarborError("--expected-source-digest is required for author")
            output = author_revision(
                load_source(Path(args.source)), _required_json(args.edits, "edits"),
                expected_source_digest=args.expected_source_digest,
            )
        elif args.command == "verify":
            state = verify_bundle(_required_json(args.bundle, "bundle"), require_win=args.require_win)
            output = {"verified": True, "state": state}
        elif args.command == "verify-portfolio":
            result = verify_portfolio(_required_json(args.bundle, "bundle"))
            output = {"verified": True, "branches": result}
        elif args.command == "checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for checkpoint")
            output = checkpoint(_required_json(args.bundle, "bundle"), args.tick)
        elif args.command == "resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for resume")
            output = resume_bundle(
                _required_json(args.bundle, "bundle"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
                require_win=args.require_win,
            )
        elif args.command == "portfolio":
            output = branch_portfolio(
                _required_json(args.bundle, "bundle"),
                _required_json(args.branches, "branches"),
            )
        else:
            source = load_source(Path(args.source))
            actions = demo_actions() if args.command == "demo" else _required_json(args.actions, "actions")
            output = export_bundle(source, actions, require_win=args.require_win)
        sys.stdout.buffer.write(canonical(output) + b"\n")
        return 0
    except HarborError as exc:
        print("harbor: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
