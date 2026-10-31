"""Read and compile original studio blueprints through canonical game_builder."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    compile_preview, list_blueprints, read_blueprint,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Browse original production briefs and build offline proof")
    ap.add_argument("--genre", help="Filter available production briefs")
    ap.add_argument("--biome", help="Filter original environments")
    ap.add_argument("--project", help="Inspect or compile one registered project")
    ap.add_argument("--compile-preview", action="store_true", help="Compile verified HTML5 maze preview")
    ap.add_argument("--materialize-batch", action="store_true",
                    help="Compile matching catalog projects into an existing output directory")
    ap.add_argument("--max-artifact-bytes", type=int, default=None,
                    help="Optional explicit export cap; default adapts to measured free disk capacity")
    ap.add_argument("--output", type=Path, help="New directory for compiled HTML")
    ap.add_argument("--search", help="Search registered original production briefs")
    ap.add_argument("--deep-search", action="store_true",
                    help="Search authored narrative/quest/asset/audio sections as well")
    ap.add_argument("--limit", type=int, default=20,
                    help="Maximum deterministic search results, 1..100")
    ap.add_argument("--play-quest", action="store_true",
                    help="Execute deterministic authored quest choices without certifying native gameplay")
    ap.add_argument("--quest-actions", help="Bounded JSON array of [stage, choice] pairs")
    ap.add_argument("--play-walk", action="store_true",
                    help="Replay authoritative walk movement and scene choices; print save receipt")
    ap.add_argument("--walk-events", metavar="JSON",
                    help="JSON array of [move|choose, value] actions to append to walk session")
    receipt_mode = ap.add_mutually_exclusive_group()
    receipt_mode.add_argument("--walk-receipt", metavar="JSON",
                              help="Previously exported source-bound walk receipt")
    receipt_mode.add_argument("--walk-receipt-stdin", action="store_true",
                              help="Read a bounded saved receipt from standard input")
    route_mode = ap.add_mutually_exclusive_group()
    route_mode.add_argument("--walk-route", action="store_true",
                            help="Include a deterministic shortest source-bound interaction route")
    route_mode.add_argument("--walk-follow-route", action="store_true",
                            help="Replay a source-verified route to the next authored marker without choosing")
    route_mode.add_argument("--walk-preview-choices", action="store_true",
                            help="Preview one authoritative choice per available branch without applying it")
    route_mode.add_argument("--walk-forecast", action="store_true",
                            help="Forecast bounded collision-checked authored choice branches without saving")
    route_mode.add_argument("--walk-commit-forecast-branch", type=int, default=None, metavar="INDEX",
                            help="Commit a canonical forecast branch by index with full replay")
    route_mode.add_argument("--walk-continuity", action="store_true",
                            help="Audit played scenes, rewards and authored ending predicates without changing the save")
    route_mode.add_argument("--walk-compare-events", metavar="JSON",
                            help="Compare this verified save to a second complete authored event history without changing it")
    route_mode.add_argument("--walk-rewind-choices", type=int, default=None, metavar="N",
                            help="Restore a verified save to before its last 1..32 authored choices")
    route_mode.add_argument("--walk-timeline", action="store_true",
                            help="Inspect bounded source-verified scene checkpoints without changing save")
    route_mode.add_argument("--walk-restore-checkpoint", type=int, default=None, metavar="INDEX",
                            help="Restore a displayed checkpoint by absolute authored choice index")
    ap.add_argument("--walk-forecast-depth", type=int, default=None, metavar="N",
                    help="Forecast at most 1..3 authored scenes (requires --walk-forecast)")
    args = ap.parse_args(argv)
    if (args.walk_forecast_depth is not None and not args.walk_forecast
            and args.walk_commit_forecast_branch is None):
        ap.error("--walk-forecast-depth requires --walk-forecast or --walk-commit-forecast-branch")
    if not args.play_walk and (args.walk_events is not None
                               or args.walk_receipt is not None
                               or args.walk_receipt_stdin or args.walk_route or args.walk_follow_route
                               or args.walk_preview_choices or args.walk_forecast
                               or args.walk_commit_forecast_branch is not None or args.walk_continuity
                               or args.walk_compare_events is not None or args.walk_rewind_choices is not None
                               or args.walk_timeline or args.walk_restore_checkpoint is not None):
        ap.error("--walk-events and --walk-receipt require --play-walk")
    if args.play_walk:
        if (not args.project or args.play_quest or args.quest_actions is not None
                or args.search is not None or args.materialize_batch
                or args.compile_preview or args.output or args.deep_search
                or args.genre or args.biome or args.limit != 20
                or args.max_artifact_bytes is not None):
            ap.error("--play-walk requires --project and excludes other modes")
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        from skeleton.ai.game_builder.studio_ecosystem_walk_replay import (
            MAX_WALK_EVENTS, MAX_WALK_RECEIPT_BYTES, export_walk_receipt,
            replay_walk, restore_walk_receipt, walk_route_hint, follow_walk_route,
            walk_choice_previews, walk_branch_forecast, commit_walk_forecast_branch,
            walk_narrative_continuity, compare_walk_sessions, validate_walk_events,
            rewind_walk_choices, walk_checkpoint_timeline, restore_walk_checkpoint,
        )
        if args.walk_restore_checkpoint is not None:
            if (args.walk_restore_checkpoint < 0
                    or not (args.walk_receipt is not None or args.walk_receipt_stdin)
                    or args.walk_events is not None):
                ap.error("--walk-restore-checkpoint requires a saved receipt, nonnegative index, and no new events")
        if args.walk_rewind_choices is not None:
            if (not 1 <= args.walk_rewind_choices <= 32
                    or not (args.walk_receipt is not None or args.walk_receipt_stdin)
                    or args.walk_events is not None):
                ap.error("--walk-rewind-choices requires a saved receipt, 1..32 choices, and no new events")
        try:
            encoded = args.walk_events if args.walk_events is not None else "[]"
            if len(encoded.encode("utf-8", "strict")) > MAX_WALK_RECEIPT_BYTES:
                raise StudioQuestError("walk events exceed input byte budget")
            actions = json.loads(encoded, parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite walk action")))
            if not isinstance(actions, list) or len(actions) > MAX_WALK_EVENTS:
                raise StudioQuestError("invalid walk event count")
            alternative_actions = None
            if args.walk_compare_events is not None:
                compare_json = args.walk_compare_events
                if len(compare_json.encode("utf-8", "strict")) > MAX_WALK_RECEIPT_BYTES:
                    raise StudioQuestError("walk comparison exceeds input byte budget")
                alternative_actions = json.loads(
                    compare_json, parse_constant=lambda _: (_ for _ in ()).throw(
                        StudioQuestError("nonfinite walk comparison action")),
                )
                if (not isinstance(alternative_actions, list)
                        or len(alternative_actions) > MAX_WALK_EVENTS):
                    raise StudioQuestError("invalid walk comparison event count")
                # Reject malformed comparisons before reading authoritative source.
                validate_walk_events(alternative_actions)
            if args.walk_receipt_stdin:
                raw = sys.stdin.buffer.read(MAX_WALK_RECEIPT_BYTES + 1)
            elif args.walk_receipt is not None:
                raw = args.walk_receipt.encode("utf-8", "strict")
            else:
                raw = None
            if raw is not None and len(raw) > MAX_WALK_RECEIPT_BYTES:
                raise StudioQuestError("walk receipt exceeds input byte budget")
            docs = read_blueprint(args.project)
            previous = (restore_walk_receipt(docs, raw, authorized=True)
                        if raw is not None else None)
            prior_events = previous.events if previous is not None else ()
            if len(prior_events) + len(actions) > MAX_WALK_EVENTS:
                raise StudioQuestError("walk replay exceeds event budget")
            session = replay_walk(docs, list(prior_events) + actions, authorized=True)
            if args.walk_restore_checkpoint is not None:
                session, checkpoint_restore = restore_walk_checkpoint(
                    session, docs, checkpoint_index=args.walk_restore_checkpoint,
                    authorized=True,
                )
                receipt = export_walk_receipt(session, docs, authorized=True)
                print(json.dumps({"receipt": json.loads(receipt),
                                  "checkpoint_restore": checkpoint_restore},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_rewind_choices is not None:
                session, rewind_receipt = rewind_walk_choices(
                    session, docs, count=args.walk_rewind_choices, authorized=True,
                )
                receipt = export_walk_receipt(session, docs, authorized=True)
                print(json.dumps({"receipt": json.loads(receipt),
                                  "choice_rewind": rewind_receipt},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_commit_forecast_branch is not None:
                session, branch_execution = commit_walk_forecast_branch(
                    session, docs, branch_index=args.walk_commit_forecast_branch,
                    depth=(args.walk_forecast_depth if args.walk_forecast_depth is not None else 2),
                    authorized=True,
                )
                receipt = export_walk_receipt(session, docs, authorized=True)
                print(json.dumps({"receipt": json.loads(receipt),
                                  "branch_execution": branch_execution},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_follow_route:
                session, route_execution = follow_walk_route(session, docs, authorized=True)
                receipt = export_walk_receipt(session, docs, authorized=True)
                print(json.dumps({"receipt": json.loads(receipt),
                                  "route_execution": route_execution},
                                 sort_keys=True, separators=(",", ":")))
            else:
                receipt = export_walk_receipt(session, docs, authorized=True)
            if args.walk_forecast:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "branch_forecast": walk_branch_forecast(
                                      session, docs, depth=(args.walk_forecast_depth
                                                           if args.walk_forecast_depth is not None else 2),
                                      authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_preview_choices:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "choice_previews": walk_choice_previews(session, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif alternative_actions is not None:
                alternative = replay_walk(docs, alternative_actions, authorized=True)
                print(json.dumps({"receipt": json.loads(receipt),
                                  "comparison": compare_walk_sessions(
                                      session, alternative, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_timeline:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "timeline": walk_checkpoint_timeline(
                                      session, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_continuity:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "narrative_continuity": walk_narrative_continuity(
                                      session, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_route:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "route": walk_route_hint(session, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif (not args.walk_follow_route and not args.walk_preview_choices
                  and not args.walk_forecast and args.walk_commit_forecast_branch is None
                  and not args.walk_continuity and alternative_actions is None
                  and args.walk_rewind_choices is None
                  and not args.walk_timeline and args.walk_restore_checkpoint is None):
                print(receipt.decode("ascii"))
        except (StudioQuestError, UnicodeError, ValueError, TypeError, OSError, RecursionError) as exc:
            ap.error(str(exc))
        return 0
    if args.play_quest:
        if (not args.project or args.search is not None or args.materialize_batch
                or args.compile_preview or args.output or args.deep_search
                or args.genre or args.biome or args.limit != 20):
            ap.error("--play-quest requires --project and excludes other modes")
        encoded = args.quest_actions or "[]"
        if len(encoded.encode("utf-8", "strict")) > 16384:
            ap.error("--quest-actions exceeds 16KiB")
        try:
            actions = json.loads(encoded, parse_constant=lambda v: (_ for _ in ()).throw(
                ValueError("nonfinite quest action")))
        except (UnicodeError, ValueError):
            ap.error("--quest-actions must be valid finite JSON")
        from skeleton.ai.game_builder.studio_ecosystem_quest import (
            start_catalog_quest, replay_quest, quest_progress,
        )
        docs, _start = start_catalog_quest(args.project, authorized=True)
        result = replay_quest(docs, actions, authorized=True)
        print(json.dumps({"receipt": result.receipt(),
                          "progress": quest_progress(result, docs)}, sort_keys=True))
        return 0
    if args.quest_actions is not None:
        ap.error("--quest-actions requires --play-quest")
    if args.search is not None:
        if args.materialize_batch or args.compile_preview or args.project or args.output:
            ap.error("--search cannot combine with compilation, project, or output")
        from skeleton.ai.game_builder.studio_ecosystem_search import search_blueprints
        print(json.dumps(search_blueprints(
            args.search, genre=args.genre, biome=args.biome,
            deep=args.deep_search, limit=args.limit,
        ), sort_keys=True))
        return 0
    if args.deep_search or args.limit != 20:
        ap.error("--deep-search and --limit require --search")
    if args.materialize_batch:
        if args.compile_preview or not args.output:
            ap.error("--materialize-batch requires --output and excludes --compile-preview")
        from skeleton.ai.game_builder.studio_ecosystem_batch import materialize_previews
        result = materialize_previews(
            args.output, authorized=True, genre=args.genre, biome=args.biome,
            project_ids=(args.project,) if args.project else None,
            max_artifact_bytes=args.max_artifact_bytes,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.compile_preview:
        if not args.project or not args.output:
            ap.error("--compile-preview requires --project and --output")
        if args.output.is_symlink() or args.output.exists():
            ap.error("--output must be a new, non-symlink location")
        project = compile_preview(args.project, authorized=True)
        from skeleton.ai.game_builder.playable_compiler import export_compiled_project
        args.output.mkdir(parents=True, exist_ok=False)
        export_compiled_project(project, args.output / "index.html", authorized=True)
        print(json.dumps({"project": args.project, "receipt": project.receipt()},
                         sort_keys=True))
    elif args.project:
        print(json.dumps(read_blueprint(args.project), sort_keys=True))
    else:
        print(json.dumps({"projects": list_blueprints(genre=args.genre, biome=args.biome)},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
