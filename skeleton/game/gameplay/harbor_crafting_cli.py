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
from .harbor_crafting_mission_compare import compare_mission_revision, verify_mission_comparison
from .harbor_crafting_package import MAX_PACKAGE_BYTES, build_package, verify_package, play_package, verify_package_play
from .harbor_crafting_market import market_report, verify_market_report, market_checkpoint, market_resume, market_futures, verify_market_futures
from .harbor_crafting_market_preview import preview_market, verify_market_preview, apply_market_preview, MAX_BYTES as MAX_PREVIEW_BYTES
from .harbor_crafting_market import MAX_BYTES as MAX_MARKET_BYTES
from .harbor_crafting_market_balance import balance_market, verify_market_balance, MAX_BYTES as MAX_BALANCE_BYTES
from .harbor_crafting_market_distribution import build_market_distribution, verify_market_distribution, play_market_distribution, verify_market_distribution_play, MAX_BYTES as MAX_DISTRIBUTION_BYTES
from .harbor_crafting_npc import npc_observations, verify_npc_observations, npc_forecast, verify_npc_forecast, MAX_BYTES as MAX_NPC_BYTES
from .harbor_crafting_journal_merge import (
    MAX_COMPARISON_BYTES, compare_journals, fast_forward_journal,
    verify_journal_comparison,
)
from .harbor_crafting_journal import (
    MAX_JOURNAL_BYTES, append_journal, create_journal, journal_at, journal_audit,
    journal_head, rewind_journal, verify_journal,
)
from .harbor_crafting_journal_transfer import (
    MAX_TRANSFER_BYTES, export_journal_package_play, verify_journal_package_play,
)
from .harbor_crafting_guidance import (
    MAX_REPORT_BYTES as MAX_GUIDANCE_BYTES,
    legal_action_report, verify_legal_action_report,
)
from .harbor_crafting_route import MAX_ROUTE_BYTES, plan_route, verify_route
from .harbor_crafting_itinerary import (
    MAX_ITINERARY_BYTES, build_itinerary, verify_itinerary,
)
from .harbor_crafting_time_trials import (
    MAX_REPORT_BYTES as MAX_TRIAL_REPORT_BYTES,
    MAX_BOARD_BYTES as MAX_TRIAL_BOARD_BYTES,
    resume_time_trial, time_trial_report, verify_time_trial_report,
    time_trial_leaderboard, verify_time_trial_leaderboard,
)
from .harbor_crafting_time_trial_authoring import (
    MAX_REVISION_BYTES as MAX_TRIAL_REVISION_BYTES,
    author_time_trial_revision, verify_time_trial_revision,
)
from .harbor_crafting_season_authoring import (
    MAX_REVISION_BYTES as MAX_SEASON_REVISION_BYTES,
    author_season_revision, verify_season_revision,
)
from .harbor_crafting_season import (
    MAX_RECORD_BYTES as MAX_SEASON_RECORD_BYTES,
    MAX_BOARD_BYTES as MAX_SEASON_BOARD_BYTES,
    MAX_SEASON_BYTES, append_season, build_season, verify_season_record,
    season_board, verify_season_board, next_season_round,
)
from .harbor_crafting_ghost_race import (
    MAX_RACE_BYTES as MAX_GHOST_RACE_BYTES, ghost_race, verify_ghost_race,
)
from .harbor_crafting_contracts import (
    MAX_BOARD_BYTES as MAX_CONTRACT_BOARD_BYTES,
    MAX_SAVE_BYTES as MAX_CONTRACT_SAVE_BYTES,
    MAX_EDITS_BYTES as MAX_CONTRACT_EDITS_BYTES,
    build_save, append_save, play_save, next_order, verify_save, edit_board, verify_edit,
)
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


def _required_json(path: str | None, name: str, maximum: int = MAX_BUNDLE_BYTES):
    if not path:
        raise HarborError("--" + name + " is required")
    return decode(_read(path, maximum), maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, export, branch and replay-verify Lantern Quay")
    parser.add_argument("command", choices=(
        "demo", "play", "verify", "checkpoint", "resume", "portfolio", "verify-portfolio", "author", "verify-author", "solve", "verify-plan", "play-live", "mission-report", "verify-mission-report", "solve-missions", "author-missions", "verify-mission-author", "mission-checkpoint", "mission-resume", "mission-portfolio", "verify-mission-portfolio", "compare-mission-revision", "verify-mission-comparison", "package-build", "package-verify", "package-play", "package-verify-play", "market-report", "verify-market", "market-checkpoint", "market-resume", "market-futures", "verify-market-futures", "market-preview", "verify-market-preview", "market-apply", "market-balance", "verify-market-balance", "market-distribution", "verify-market-distribution", "market-distribution-play", "verify-market-distribution-play", "npc-report", "verify-npc-report", "npc-forecast", "verify-npc-forecast", "journal-init", "journal-append", "journal-verify", "journal-export", "journal-at", "journal-rewind", "journal-audit", "journal-compare", "journal-verify-comparison", "journal-fast-forward", "legal-actions", "verify-legal-actions", "journal-package-play", "journal-verify-package-play", "route-plan", "route-verify", "itinerary-build", "itinerary-verify", "trial-run", "trial-verify", "trial-resume", "trial-leaderboard", "trial-verify-leaderboard", "trial-author", "trial-verify-author", "trial-live", "ghost-race", "ghost-verify", "season-init", "season-append", "season-verify", "season-board", "season-board-verify", "season-author", "season-verify-author", "season-next", "season-live", "contract-init", "contract-next", "contract-play", "contract-append", "contract-verify", "contract-author", "contract-verify-author"
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
    parser.add_argument("--comparison", help="Portable replay-derived mission revision comparison")
    parser.add_argument("--package", help="Portable original game package")
    parser.add_argument("--preview", help="Portable source-bound market preview JSON")
    parser.add_argument("--play", help="Portable gameplay session produced from a package")
    parser.add_argument("--preview-bundle", help="Optional canonical gameplay bundle for edited mission preview")
    parser.add_argument("--require-all", action="store_true", help="Require every authored mission to be earned")
    parser.add_argument("--journal", help="Portable replay journal JSON")
    parser.add_argument("--other-journal", help="Candidate journal for reconciliation")
    parser.add_argument("--expected-journal-digest", help="CAS journal lease")
    parser.add_argument("--revision-index", type=int, help="Historical journal revision")
    parser.add_argument("--goal", help="Route destination as x,y")
    parser.add_argument("--route", help="Portable replay-verified route JSON")
    parser.add_argument("--stops", help="JSON array of route-and-interaction stops")
    parser.add_argument("--itinerary", help="Portable replay-verified itinerary JSON")
    parser.add_argument("--trial", help="Authored time trial course JSON")
    parser.add_argument("--reports", help="JSON array of replay-verified time trial reports")
    parser.add_argument("--board", help="Portable time trial leaderboard JSON")
    parser.add_argument("--season", help="Source-bound authored championship season JSON")
    parser.add_argument("--season-edits", help="Transactional season authoring edits JSON")
    parser.add_argument("--season-revision", help="Replay-verifiable season authoring revision JSON")
    parser.add_argument("--preview-season-record", help="Existing earned season save for edit preview")
    parser.add_argument("--season-record", help="Portable replay-verified season save JSON")
    parser.add_argument("--season-records", help="JSON array of replay-verified season saves")
    parser.add_argument("--season-board", help="Portable replay-verified season standings JSON")
    parser.add_argument("--expected-season-digest", help="CAS lease for season continuation")
    parser.add_argument("--contracts", help="Authored source-bound contract board")
    parser.add_argument("--contract-save", help="Portable replay-verified contract save")
    parser.add_argument("--contract-edits", help="Transactional contract board edits")
    parser.add_argument("--contract-revision", help="Replay-verifiable contract edit revision")
    parser.add_argument("--expected-contract-digest", help="CAS lease for contract save or board")
    parser.add_argument("--ghost-bundle", help="Verified opponent save for ghost racing")
    parser.add_argument("--trial-edits", help="JSON array of transactional time trial edits")
    parser.add_argument("--trial-revision", help="Portable time trial course revision JSON")
    parser.add_argument("--expected-course-digest", help="CAS lease for time trial course")
    parser.add_argument("--max-steps", type=int, default=64, help="Bounded route search horizon")
    parser.add_argument("--require-win", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "contract-init":
            output = build_save(load_source(Path(args.source)),
                _required_json(args.contracts, "contracts", MAX_CONTRACT_BOARD_BYTES), [])
        elif args.command == "contract-next":
            output = next_order(_required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES))
        elif args.command == "contract-verify":
            output = {"verified": True, **verify_save(
                _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES))}
        elif args.command in ("contract-play", "contract-append"):
            if not args.expected_contract_digest:
                raise HarborError("--expected-contract-digest is required")
            save = _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES)
            if args.command == "contract-play":
                output = play_save(save, _required_json(args.actions, "actions"),
                    expected_digest=args.expected_contract_digest)
            else:
                output = append_save(save, _required_json(args.bundle, "bundle"),
                    expected_digest=args.expected_contract_digest)
        elif args.command == "contract-author":
            if not args.expected_source_digest or not args.expected_contract_digest:
                raise HarborError("--expected-source-digest and --expected-contract-digest are required")
            output = edit_board(load_source(Path(args.source)),
                _required_json(args.contracts, "contracts", MAX_CONTRACT_BOARD_BYTES),
                _required_json(args.contract_edits, "contract-edits", MAX_CONTRACT_BOARD_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_board_digest=args.expected_contract_digest)
        elif args.command == "contract-verify-author":
            output = {"verified": True, **verify_edit(
                _required_json(args.contract_revision, "contract-revision", MAX_CONTRACT_EDITS_BYTES))}
        elif args.command in ("season-next", "season-live"):
            next_round = next_season_round(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES))
            if args.command == "season-live":
                if next_round["status"] != "ready":
                    raise HarborError("season already complete")
                return play_live(
                    next_round["source"], sys.stdin, sys.stdout,
                    course=next_round["round"]["course"],
                )
            output = next_round
        elif args.command == "season-author":
            if not args.expected_source_digest or not args.expected_season_digest:
                raise HarborError("--expected-source-digest and --expected-season-digest are required")
            output = author_season_revision(
                load_source(Path(args.source)),
                _required_json(args.season, "season", MAX_SEASON_BYTES),
                _required_json(args.season_edits, "season-edits", MAX_SEASON_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_season_digest=args.expected_season_digest,
                preview_record=_required_json(
                    args.preview_season_record, "preview-season-record", MAX_SEASON_RECORD_BYTES
                ) if args.preview_season_record else None,
            )
        elif args.command == "season-verify-author":
            output = {"verified": True, **verify_season_revision(
                _required_json(args.season_revision, "season-revision", MAX_SEASON_REVISION_BYTES))}
        elif args.command == "season-init":
            output = build_season(
                load_source(Path(args.source)),
                _required_json(args.season, "season", MAX_SEASON_BYTES), [],
            )
        elif args.command == "season-append":
            if not args.expected_season_digest:
                raise HarborError("--expected-season-digest is required")
            output = append_season(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES),
                _required_json(args.bundle, "bundle"),
                expected_record_digest=args.expected_season_digest,
            )
        elif args.command == "season-verify":
            output = {"verified": True, **verify_season_record(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES))}
        elif args.command == "season-board":
            output = season_board(
                _required_json(args.season_records, "season-records", MAX_SEASON_BOARD_BYTES))
        elif args.command == "season-board-verify":
            output = {"verified": True, "ranking": verify_season_board(
                _required_json(args.season_board, "season-board", MAX_SEASON_BOARD_BYTES))}
        elif args.command == "ghost-race":
            output = ghost_race(
                _required_json(args.bundle, "bundle"),
                _required_json(args.ghost_bundle, "ghost-bundle"),
                _required_json(args.trial, "trial"),
                expected_player_terminal_digest=args.expected_terminal_digest,
            )
        elif args.command == "ghost-verify":
            output = {"verified": True, **verify_ghost_race(
                _required_json(args.report, "report", MAX_GHOST_RACE_BYTES))}
        elif args.command == "trial-author":
            if not args.expected_course_digest or not args.expected_source_digest:
                raise HarborError("--expected-course-digest and --expected-source-digest are required")
            output = author_time_trial_revision(
                _required_json(args.trial, "trial"), load_source(Path(args.source)),
                _required_json(args.trial_edits, "trial-edits"),
                expected_course_digest=args.expected_course_digest,
                expected_source_digest=args.expected_source_digest,
                preview_bundle=_required_json(args.preview_bundle, "preview-bundle")
                if args.preview_bundle else None,
            )
        elif args.command == "trial-verify-author":
            output = {"verified": True, **verify_time_trial_revision(
                _required_json(args.trial_revision, "trial-revision", MAX_TRIAL_REVISION_BYTES))}
        elif args.command == "trial-run":
            output = time_trial_report(
                _required_json(args.bundle, "bundle"),
                _required_json(args.trial, "trial"),
                require_finish=args.require_win,
            )
        elif args.command == "trial-verify":
            output = {"verified": True, **verify_time_trial_report(
                _required_json(args.report, "report", MAX_TRIAL_REPORT_BYTES),
                require_finish=args.require_win,
            )}
        elif args.command == "trial-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required")
            output = resume_time_trial(
                _required_json(args.bundle, "bundle"),
                _required_json(args.trial, "trial"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
                require_finish=args.require_win,
            )
        elif args.command == "trial-leaderboard":
            output = time_trial_leaderboard(
                _required_json(args.reports, "reports", MAX_TRIAL_BOARD_BYTES))
        elif args.command == "trial-verify-leaderboard":
            output = {"verified": True, "ranking": verify_time_trial_leaderboard(
                _required_json(args.board, "board", MAX_TRIAL_BOARD_BYTES))}
        elif args.command == "itinerary-build":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required")
            output = build_itinerary(
                _required_json(args.bundle, "bundle"),
                _required_json(args.stops, "stops"),
                expected_terminal_digest=args.expected_terminal_digest,
                max_steps=args.max_steps,
            )
        elif args.command == "itinerary-verify":
            output = {"verified": True, **verify_itinerary(
                _required_json(args.itinerary, "itinerary", MAX_ITINERARY_BYTES))}
        elif args.command == "route-plan":
            if not args.goal or not args.expected_terminal_digest:
                raise HarborError("--goal and --expected-terminal-digest are required")
            coordinates = args.goal.split(",")
            if len(coordinates) != 2 or any(not part.isascii() or not part.isdecimal() for part in coordinates):
                raise HarborError("--goal must be x,y")
            output = plan_route(
                _required_json(args.bundle, "bundle"),
                [int(part) for part in coordinates],
                expected_terminal_digest=args.expected_terminal_digest,
                max_steps=args.max_steps,
            )
        elif args.command == "route-verify":
            output = {"verified": True, **verify_route(
                _required_json(args.route, "route", MAX_ROUTE_BYTES))}
        elif args.command == "journal-package-play":
            output = export_journal_package_play(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.package, "package", MAX_PACKAGE_BYTES),
                require_all=args.require_all,
            )
        elif args.command == "journal-verify-package-play":
            output = {"verified": True, **verify_journal_package_play(
                _required_json(args.play, "play", MAX_TRANSFER_BYTES),
                require_all=args.require_all,
            )}
        elif args.command == "legal-actions":
            output = legal_action_report(_required_json(args.bundle, "bundle"))
        elif args.command == "verify-legal-actions":
            output = {"verified": True, "legal_actions": verify_legal_action_report(
                _required_json(args.report, "report", MAX_GUIDANCE_BYTES))}
        elif args.command == "journal-compare":
            output = compare_journals(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.other_journal, "other-journal", MAX_JOURNAL_BYTES),
            )
        elif args.command == "journal-verify-comparison":
            output = {"verified": True, **verify_journal_comparison(
                _required_json(args.comparison, "comparison", MAX_COMPARISON_BYTES))}
        elif args.command == "journal-fast-forward":
            if not args.expected_journal_digest:
                raise HarborError("--expected-journal-digest is required")
            output = fast_forward_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.other_journal, "other-journal", MAX_JOURNAL_BYTES),
                expected_journal_digest=args.expected_journal_digest,
            )
        elif args.command == "journal-init":
            output = create_journal(_required_json(args.bundle, "bundle"))
        elif args.command == "journal-verify":
            output = {"verified": True, **verify_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES))}
        elif args.command == "journal-export":
            output = journal_head(_required_json(args.journal, "journal", MAX_JOURNAL_BYTES))
        elif args.command == "journal-audit":
            output = journal_audit(_required_json(args.journal, "journal", MAX_JOURNAL_BYTES))
        elif args.command == "journal-at":
            if args.revision_index is None:
                raise HarborError("--revision-index is required for journal-at")
            output = journal_at(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                args.revision_index,
            )
        elif args.command == "journal-rewind":
            if args.revision_index is None or not args.expected_journal_digest:
                raise HarborError("--revision-index and --expected-journal-digest are required")
            output = rewind_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                args.revision_index, expected_journal_digest=args.expected_journal_digest,
            )
        elif args.command == "journal-append":
            if not args.expected_journal_digest:
                raise HarborError("--expected-journal-digest is required")
            output = append_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.actions, "actions"),
                expected_journal_digest=args.expected_journal_digest,
                require_win=args.require_win,
            )
        elif args.command == "verify-npc-forecast":
            output = {"verified": True, "terminal": verify_npc_forecast(
                _required_json(args.report, "report", MAX_NPC_BYTES))}
        elif args.command == "npc-forecast":
            if args.tick is None:
                raise HarborError("--tick is required for npc-forecast")
            output = npc_forecast(_required_json(args.bundle, "bundle"), args.tick)
        elif args.command == "verify-npc-report":
            output = {"verified": True, "terminal": verify_npc_observations(
                _required_json(args.report, "report", MAX_NPC_BYTES))}
        elif args.command == "npc-report":
            output = npc_observations(_required_json(args.bundle, "bundle"))
        elif args.command == "verify-market-distribution-play":
            output = {"verified": True, "totals": verify_market_distribution_play(
                _required_json(args.play, "play", MAX_DISTRIBUTION_BYTES * 2),
                require_all=args.require_all)}
        elif args.command == "market-distribution-play":
            output = play_market_distribution(
                _required_json(args.package, "package", MAX_DISTRIBUTION_BYTES),
                _required_json(args.actions, "actions"), require_all=args.require_all)
        elif args.command == "verify-market-distribution":
            output = {"verified": True, **verify_market_distribution(
                _required_json(args.package, "package", MAX_DISTRIBUTION_BYTES))}
        elif args.command == "market-distribution":
            output = build_market_distribution(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice)
        elif args.command == "verify-market-balance":
            output = {"verified": True, **verify_market_balance(
                _required_json(args.comparison, "comparison", MAX_BALANCE_BYTES))}
        elif args.command == "market-balance":
            if not args.expected_source_digest:
                raise HarborError("--expected-source-digest is required for market-balance")
            output = balance_market(
                load_source(Path(args.source)), decode(_read(args.missions)),
                _required_json(args.edits, "edits"),
                expected_source_digest=args.expected_source_digest, choice=args.choice)
        elif args.command == "market-apply":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for market-apply")
            output = apply_market_preview(
                _required_json(args.preview, "preview", MAX_PREVIEW_BYTES),
                expected_terminal_digest=args.expected_terminal_digest, require_win=args.require_win)
        elif args.command == "verify-market-preview":
            output = {"verified": True, **verify_market_preview(
                _required_json(args.preview, "preview", MAX_PREVIEW_BYTES))}
        elif args.command == "market-preview":
            output = preview_market(
                _required_json(args.bundle, "bundle"), _required_json(args.actions, "actions"))
        elif args.command == "verify-market-futures":
            output = {"verified": True, "branches": verify_market_futures(
                _required_json(args.report, "report", MAX_MARKET_BYTES * 4))}
        elif args.command == "market-futures":
            output = market_futures(_required_json(args.bundle, "bundle"))
        elif args.command == "market-checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for market-checkpoint")
            output = market_checkpoint(_required_json(args.report, "report", MAX_MARKET_BYTES), args.tick)
        elif args.command == "market-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for market-resume")
            output = market_resume(
                _required_json(args.report, "report", MAX_MARKET_BYTES), _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest, require_win=args.require_win)
        elif args.command == "verify-market":
            output = {"verified": True, "totals": verify_market_report(
                _required_json(args.report, "report", MAX_MARKET_BYTES))}
        elif args.command == "market-report":
            output = market_report(_required_json(args.bundle, "bundle"))
        elif args.command == "package-verify-play":
            output = {"verified": True, **verify_package_play(
                _required_json(args.play, "play"), require_all=args.require_all)}
        elif args.command == "package-play":
            output = play_package(
                _required_json(args.package, "package"), _required_json(args.actions, "actions"),
                require_all=args.require_all)
        elif args.command == "package-verify":
            output = {"verified": True, **verify_package(_required_json(args.package, "package"))}
        elif args.command == "package-build":
            output = build_package(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice)
        elif args.command == "verify-mission-comparison":
            output = {"verified": True, **verify_mission_comparison(
                _required_json(args.comparison, "comparison"))}
        elif args.command == "compare-mission-revision":
            output = compare_mission_revision(
                _required_json(args.mission_revision, "mission-revision"),
                _required_json(args.bundle, "bundle"))
        elif args.command == "verify-mission-portfolio":
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
        elif args.command == "trial-live":
            return play_live(
                load_source(Path(args.source)), sys.stdin, sys.stdout,
                course=_required_json(args.trial, "trial"),
            )
        elif args.command == "play-live":
            return play_live(load_source(Path(args.source)), sys.stdin, sys.stdout)
        elif args.command == "verify-plan":
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
