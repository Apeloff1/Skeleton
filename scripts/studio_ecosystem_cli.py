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
    ap.add_argument("--author-revision", action="store_true",
                    help="Apply bounded source-leased prose edits and export an offline playable bundle")
    ap.add_argument("--faction-plan", action="store_true",
                    help="Plan a shortest replay-verified original faction negotiation")
    ap.add_argument("--faction-goal", metavar="JSON",
                    help='Exact faction threshold, e.g. {"faction_id":"residents","minimum":3}')
    ap.add_argument("--faction-reputation", action="store_true",    ap.add_argument("--faction-reputation", action="store_true",
                    help="Replay original authored faction reputation consequences")
    ap.add_argument("--faction-decisions", metavar="JSON",
                    help="Bounded JSON list of distinct authored faction decisions")
    ap.add_argument("--faction-expected-digest",
                    help="Optional exact source SHA-256 for faction replay continuation")
    ap.add_argument("--ending-plan", action="store_true",
                    help="Replay-verify a deterministic authored quest route toward one ending")
    ap.add_argument("--ending-id", help="Exact authored ending ID for --ending-plan")
    ap.add_argument("--ending-choices", metavar="JSON",
                    help="Optional exact stage-to-alternative map for source-verified ending planning")
    ap.add_argument("--revision-lineage", action="store_true",
                    help="Verify an ordered source-leased original authoring history")
    ap.add_argument("--revision-lineage-source", type=Path, action="append",
                    help="One verified revision bundle in chronological order, at most eight")
    ap.add_argument("--merge-revisions", action="store_true",
                    help="Merge two independently verified original prose revisions against a common base")
    ap.add_argument("--merge-left-source", type=Path,
                    help="Verified first authored revision bundle")
    ap.add_argument("--merge-right-source", type=Path,
                    help="Verified second authored revision bundle")
    ap.add_argument("--cherry-pick-revision", action="store_true",
                    help="Transplant selected donor prose into a verified target revision")
    ap.add_argument("--cherry-pick-paths", metavar="JSON",
                    help="Exact selected authored source paths, e.g. [[\\"narrative\\",\\"premise\\"]]")
    ap.add_argument("--revision-impact", action="store_true",
                    help="Compare canonical source against a verified authored revision")
    ap.add_argument("--revision-compare-source", type=Path,
                    help="Verified revision directory to compare with canonical or earlier revision")
    ap.add_argument("--revision-source", type=Path,
                    help="Reopen a previously verified authored revision directory")
    ap.add_argument("--revision-request", metavar="JSON",
                    help="Typed original-world revision with expected source digest")
    ap.add_argument("--audit-canon", action="store_true",
                    help="Audit original scene/era/cast continuity and ending obligations")
    ap.add_argument("--play-quest", action="store_true",
                    help="Execute deterministic authored quest choices without certifying native gameplay")
    ap.add_argument("--quest-actions", help="Bounded JSON array of [stage, choice] pairs")
    ap.add_argument("--walk-audit-catalog", action="store_true",
                    help="Audit a bounded page of original catalog authored walk choices")
    ap.add_argument("--walk-audit-offset", type=int, default=0,
                    help="Zero-based offset for --walk-audit-catalog")
    ap.add_argument("--walk-audit-batch-size", type=int, default=2,
                    help="Projects per catalog audit page (1..4)")
    ap.add_argument("--walk-audit-expected-digest",
                    help="Required catalog SHA-256 from the preceding page for nonzero offset")
    ap.add_argument("--walk-audit-aggregate-stdin", action="store_true",
                    help="Revalidate and aggregate up to four canonical catalog audit pages from stdin")
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
    route_mode.add_argument("--walk-audit-choices", action="store_true",
                            help="Verify authored alternatives by collision-checked source replay")
    route_mode.add_argument("--walk-canon-journal", action="store_true",
                            help="Read authored era, cast, scene and plot-beat canon for played choices")
    ap.add_argument("--walk-journal-offset", type=int, default=0)
    ap.add_argument("--walk-journal-limit", type=int, default=8)
    ap.add_argument("--walk-journal-expected-session-digest")
    ap.add_argument("--walk-journal-expected-source-digest")
    route_mode.add_argument("--walk-story-transcript", action="store_true",
                            help="Inspect verified authored scene choices without changing save")
    ap.add_argument("--walk-story-offset", type=int, default=0,
                    help="Zero-based completed-scene page offset for --walk-story-transcript")
    ap.add_argument("--walk-story-limit", type=int, default=32,
                    help="Completed scenes per transcript page, 1..32")
    ap.add_argument("--walk-story-expected-digest",
                    help="Session SHA-256 required to continue a transcript from nonzero offset")
    route_mode.add_argument("--walk-timeline", action="store_true",
                            help="Inspect bounded source-verified scene checkpoints without changing save")
    route_mode.add_argument("--walk-restore-checkpoint", type=int, default=None, metavar="INDEX",
                            help="Restore a displayed checkpoint by absolute authored choice index")
    ap.add_argument("--walk-forecast-depth", type=int, default=None, metavar="N",
                    help="Forecast at most 1..3 authored scenes (requires --walk-forecast)")
    args = ap.parse_args(argv)
    if (not args.walk_canon_journal and
            (args.walk_journal_offset != 0 or args.walk_journal_limit != 8
             or args.walk_journal_expected_session_digest is not None
             or args.walk_journal_expected_source_digest is not None)):
        ap.error("--walk-journal-* options require --walk-canon-journal")
    if (not args.walk_story_transcript and
            (args.walk_story_offset != 0 or args.walk_story_limit != 32
             or args.walk_story_expected_digest is not None)):
        ap.error("--walk-story-* page options require --walk-story-transcript")
    if (args.walk_forecast_depth is not None and not args.walk_forecast
            and args.walk_commit_forecast_branch is None):
        ap.error("--walk-forecast-depth requires --walk-forecast or --walk-commit-forecast-branch")
    if not args.play_walk and (args.walk_events is not None
                               or args.walk_receipt is not None
                               or args.walk_receipt_stdin or args.walk_route or args.walk_follow_route
                               or args.walk_preview_choices or args.walk_forecast
                               or args.walk_commit_forecast_branch is not None or args.walk_continuity
                               or args.walk_compare_events is not None or args.walk_rewind_choices is not None
                               or args.walk_timeline or args.walk_story_transcript or args.walk_canon_journal
                               or args.walk_audit_choices
                               or args.walk_restore_checkpoint is not None):
        ap.error("--walk-events and --walk-receipt require --play-walk")
    if args.walk_audit_aggregate_stdin:
        if (args.walk_audit_catalog or args.play_walk or args.play_quest
                or args.project or args.compile_preview or args.materialize_batch
                or args.output or args.search is not None or args.deep_search
                or args.limit != 20 or args.quest_actions is not None
                or args.genre or args.biome or args.max_artifact_bytes is not None
                or args.walk_audit_offset != 0 or args.walk_audit_batch_size != 2
                or args.walk_audit_expected_digest is not None):
            ap.error("--walk-audit-aggregate-stdin excludes other catalog and gameplay modes")
        from skeleton.ai.game_builder.studio_ecosystem_walk_coverage_batch import (
            merge_catalog_walk_audits, MAX_CATALOG_MERGE_BYTES,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        raw = sys.stdin.buffer.read(MAX_CATALOG_MERGE_BYTES + 1)
        if len(raw) > MAX_CATALOG_MERGE_BYTES:
            ap.error("catalog audit aggregate input exceeds byte budget")
        def _unique_pairs(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate catalog audit JSON field")
                obj[key] = value
            return obj
        try:
            pages = json.loads(raw, object_pairs_hook=_unique_pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(
                                   ValueError("nonfinite catalog audit JSON")))
            result = merge_catalog_walk_audits(pages, authorized=True)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.walk_audit_catalog:
        if (args.play_walk or args.play_quest or args.project or args.compile_preview
                or args.materialize_batch or args.output or args.search is not None
                or args.deep_search or args.limit != 20 or args.quest_actions is not None
                or args.max_artifact_bytes is not None):
            ap.error("--walk-audit-catalog excludes gameplay, search and export modes")
        from skeleton.ai.game_builder.studio_ecosystem_walk_coverage_batch import (
            audit_catalog_walk_choices,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            result = audit_catalog_walk_choices(
                authorized=True, genre=args.genre, biome=args.biome,
                offset=args.walk_audit_offset, limit=args.walk_audit_batch_size,
                expected_catalog_digest=args.walk_audit_expected_digest,
            )
        except (StudioQuestError, ValueError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if (args.walk_audit_offset != 0 or args.walk_audit_batch_size != 2
            or args.walk_audit_expected_digest is not None):
        ap.error("--walk-audit-offset, --walk-audit-batch-size and --walk-audit-expected-digest require --walk-audit-catalog")
    if args.faction_plan:
        if (not args.project or args.faction_goal is None
                or args.faction_reputation or args.ending_plan or args.author_revision
                or args.cherry_pick_revision or args.merge_revisions
                or args.revision_impact or args.revision_lineage or args.audit_canon
                or args.play_walk or args.play_quest or args.compile_preview
                or args.materialize_batch or args.walk_audit_catalog
                or args.walk_audit_aggregate_stdin or args.search is not None
                or args.deep_search or args.genre or args.biome or args.output
                or args.quest_actions is not None or args.revision_source is not None
                or args.limit != 20 or args.max_artifact_bytes is not None):
            ap.error("--faction-plan requires --project and --faction-goal, excluding other modes")
        from skeleton.ai.game_builder.studio_ecosystem_faction_plan import (
            plan_faction_negotiation,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            def unique(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise StudioQuestError("duplicate faction plan JSON key")
                    obj[key] = value
                return obj
            goal_raw = args.faction_goal.encode("utf-8", "strict")
            decisions_raw = (args.faction_decisions or "[]").encode("utf-8", "strict")
            if len(goal_raw) > 4096 or len(decisions_raw) > 8192:
                raise StudioQuestError("faction plan input exceeds byte budget")
            parse = dict(object_pairs_hook=unique, parse_constant=lambda _: (
                _ for _ in ()).throw(StudioQuestError("nonfinite faction plan JSON")))
            goal = json.loads(goal_raw, **parse)
            decisions = json.loads(decisions_raw, **parse)
            if (type(goal) is not dict
                    or set(goal) not in ({"faction_id", "minimum"},
                                        {"faction_id", "maximum"})):
                raise StudioQuestError("invalid faction plan goal fields")
            result = plan_faction_negotiation(
                read_blueprint(args.project), decisions=decisions,
                expected_source_digest=args.faction_expected_digest,
                authorized=True, **goal)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.faction_goal is not None:
        ap.error("--faction-goal requires --faction-plan")
    if args.faction_reputation:
    if args.faction_reputation:
        if (not args.project or args.ending_plan or args.author_revision
                or args.cherry_pick_revision or args.merge_revisions
                or args.revision_impact or args.revision_lineage or args.audit_canon
                or args.play_walk or args.play_quest or args.compile_preview
                or args.materialize_batch or args.walk_audit_catalog
                or args.walk_audit_aggregate_stdin or args.search is not None
                or args.deep_search or args.genre or args.biome or args.output
                or args.quest_actions is not None or args.revision_source is not None
                or args.limit != 20 or args.max_artifact_bytes is not None):
            ap.error("--faction-reputation requires --project and excludes other modes")
        from skeleton.ai.game_builder.studio_ecosystem_faction_reputation import (
            simulate_faction_reputation,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            encoded = args.faction_decisions or "[]"
            if len(encoded.encode("utf-8", "strict")) > 8192:
                raise StudioQuestError("faction decisions exceed byte budget")
            decisions = json.loads(
                encoded, parse_constant=lambda _: (_ for _ in ()).throw(
                    StudioQuestError("nonfinite faction decision JSON")))
            result = simulate_faction_reputation(
                read_blueprint(args.project), decisions, authorized=True,
                expected_source_digest=args.faction_expected_digest)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.faction_decisions is not None or args.faction_expected_digest is not None:
        ap.error("--faction-decisions and --faction-expected-digest require --faction-reputation")
    if args.ending_plan:
        if (not args.project or not args.ending_id or args.cherry_pick_revision
                or args.play_quest
                or args.play_walk or args.author_revision or args.merge_revisions
                or args.revision_lineage or args.revision_impact or args.audit_canon
                or args.compile_preview or args.materialize_batch
                or args.walk_audit_catalog or args.walk_audit_aggregate_stdin
                or args.search is not None or args.deep_search or args.genre or args.biome
                or args.output is not None or args.limit != 20
                or args.max_artifact_bytes is not None or args.revision_source is not None):
            ap.error("--ending-plan requires --project and --ending-id, excluding other modes")
        from skeleton.ai.game_builder.studio_ecosystem_ending_plan import plan_authored_ending
        from skeleton.ai.game_builder.studio_ecosystem_quest import (
            StudioQuestError, replay_quest,
        )
        try:
            encoded = args.quest_actions or "[]"
            if len(encoded.encode("utf-8", "strict")) > 16384:
                raise StudioQuestError("ending plan actions exceed byte budget")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise StudioQuestError("duplicate ending plan JSON key")
                    result[key] = value
                return result
            actions = json.loads(encoded, object_pairs_hook=unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(
                                     StudioQuestError("nonfinite ending plan JSON")))
            preferred = None
            if args.ending_choices is not None:
                if len(args.ending_choices.encode("utf-8", "strict")) > 8192:
                    raise StudioQuestError("ending preferences exceed byte budget")
                preferred = json.loads(
                    args.ending_choices, object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        StudioQuestError("nonfinite ending preferences")))
            docs = read_blueprint(args.project)
            session = replay_quest(docs, actions, authorized=True)
            result = plan_authored_ending(
                docs, ending_id=args.ending_id, session=session,
                preferred_choices=preferred, authorized=True)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.ending_id is not None:
        ap.error("--ending-id requires --ending-plan")
    if args.ending_choices is not None:
        ap.error("--ending-choices requires --ending-plan")
    if args.revision_lineage:
        if (not args.project or not args.revision_lineage_source
                or len(args.revision_lineage_source) > 8 or args.output is not None
                or args.author_revision or args.merge_revisions or args.revision_impact
                or args.audit_canon or args.play_walk or args.play_quest
                or args.compile_preview or args.materialize_batch
                or args.walk_audit_catalog or args.walk_audit_aggregate_stdin
                or args.search is not None or args.deep_search or args.genre or args.biome
                or args.quest_actions is not None or args.revision_request is not None
                or args.revision_compare_source is not None or args.merge_left_source is not None
                or args.merge_right_source is not None or args.limit != 20
                or args.max_artifact_bytes is not None):
            ap.error("--revision-lineage requires --project and 1..8 ordered revision sources")
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import load_revision_bundle
        from skeleton.ai.game_builder.studio_ecosystem_author_lineage import trace_canon_lineage
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            base = (load_revision_bundle(args.revision_source, authorized=True,
                                         project_id=args.project)[0]
                    if args.revision_source is not None else read_blueprint(args.project))
            steps = [load_revision_bundle(path, authorized=True, project_id=args.project)
                     for path in args.revision_lineage_source]
            result = trace_canon_lineage(base, steps, authorized=True)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.revision_lineage_source is not None:
        ap.error("--revision-lineage-source requires --revision-lineage")
    if args.merge_revisions:
        if (not args.project or args.merge_left_source is None
                or args.merge_right_source is None or args.output is None
                or args.author_revision or args.revision_impact or args.audit_canon
                or args.play_walk or args.play_quest or args.compile_preview
                or args.materialize_batch or args.walk_audit_catalog
                or args.walk_audit_aggregate_stdin or args.search is not None
                or args.deep_search or args.genre or args.biome
                or args.quest_actions is not None or args.revision_request is not None
                or args.revision_compare_source is not None or args.limit != 20
                or args.max_artifact_bytes is not None):
            ap.error("--merge-revisions requires --project, both verified sources and new --output")
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
            load_revision_bundle, write_revision_bundle,
        )
        from skeleton.ai.game_builder.studio_ecosystem_author_merge import merge_canon_revisions
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            base = (load_revision_bundle(args.revision_source, authorized=True,
                                         project_id=args.project)[0]
                    if args.revision_source is not None else read_blueprint(args.project))
            left = load_revision_bundle(args.merge_left_source, authorized=True,
                                        project_id=args.project)[0]
            right = load_revision_bundle(args.merge_right_source, authorized=True,
                                         project_id=args.project)[0]
            merged, html, receipt, impact = merge_canon_revisions(
                base, left, right, authorized=True)
            write_revision_bundle(args.output, merged, html, receipt)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps({"receipt": receipt, "impact": impact},
                         sort_keys=True, separators=(",", ":")))
        return 0
    if args.merge_left_source is not None or args.merge_right_source is not None:
        ap.error("--merge-left-source and --merge-right-source require --merge-revisions")
    if args.cherry_pick_revision:
        if (not args.project or args.revision_compare_source is None
                or args.cherry_pick_paths is None or args.output is None
                or args.author_revision or args.merge_revisions or args.revision_lineage
                or args.revision_impact or args.audit_canon or args.ending_plan
                or args.play_walk or args.play_quest or args.compile_preview
                or args.materialize_batch or args.walk_audit_catalog
                or args.walk_audit_aggregate_stdin or args.search is not None
                or args.deep_search or args.genre or args.biome
                or args.quest_actions is not None or args.revision_request is not None
                or args.limit != 20 or args.max_artifact_bytes is not None):
            ap.error("--cherry-pick-revision requires --project, donor, paths and new --output")
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
            load_revision_bundle, write_revision_bundle,
        )
        from skeleton.ai.game_builder.studio_ecosystem_author_cherry_pick import (
            cherry_pick_canon_revision,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            if len(args.cherry_pick_paths.encode("utf-8", "strict")) > 8192:
                raise StudioQuestError("authored cherry-pick path request too large")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise StudioQuestError("duplicate cherry-pick JSON key")
                    result[key] = value
                return result
            paths = json.loads(
                args.cherry_pick_paths, object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    StudioQuestError("nonfinite cherry-pick path JSON")),
            )
            base = read_blueprint(args.project)
            donor = load_revision_bundle(
                args.revision_compare_source, authorized=True, project_id=args.project)[0]
            target = (load_revision_bundle(args.revision_source, authorized=True,
                                           project_id=args.project)[0]
                      if args.revision_source is not None else base)
            revised, html, receipt, impact = cherry_pick_canon_revision(
                base, donor, target, paths, authorized=True)
            write_revision_bundle(args.output, revised, html, receipt)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps({"receipt": receipt, "impact": impact},
                         sort_keys=True, separators=(",", ":")))
        return 0
    if args.cherry_pick_paths is not None:
        ap.error("--cherry-pick-paths requires --cherry-pick-revision")
    if args.revision_impact:
        if (not args.project or args.revision_compare_source is None
                or args.author_revision or args.audit_canon or args.play_walk
                or args.play_quest or args.walk_audit_catalog or args.walk_audit_aggregate_stdin
                or args.compile_preview or args.materialize_batch or args.output
                or args.search is not None or args.deep_search or args.genre or args.biome
                or args.quest_actions is not None or args.limit != 20
                or args.max_artifact_bytes is not None or args.revision_request is not None):
            ap.error("--revision-impact requires --project and --revision-compare-source")
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import load_revision_bundle
        from skeleton.ai.game_builder.studio_ecosystem_revision_impact import compare_revision_sources
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            before = (load_revision_bundle(args.revision_source, authorized=True,
                                           project_id=args.project)[0]
                      if args.revision_source is not None else read_blueprint(args.project))
            after = load_revision_bundle(args.revision_compare_source, authorized=True,
                                         project_id=args.project)[0]
            result = compare_revision_sources(before, after, authorized=True)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.revision_compare_source is not None:
        ap.error("--revision-compare-source requires --revision-impact")
    if args.author_revision:
        if (not args.project or args.revision_request is None or args.output is None
                or args.audit_canon or args.play_walk or args.play_quest
                or args.walk_audit_catalog or args.walk_audit_aggregate_stdin
                or args.compile_preview or args.materialize_batch
                or args.search is not None or args.deep_search or args.genre or args.biome
                or args.quest_actions is not None or args.limit != 20
                or args.max_artifact_bytes is not None):
            ap.error("--author-revision requires --project, --revision-request and new --output directory")
        from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
            MAX_REQUEST_BYTES, preview_canon_revision, write_revision_bundle,
            load_revision_bundle,
        )
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            encoded = args.revision_request.encode("utf-8", "strict")
            if len(encoded) > MAX_REQUEST_BYTES:
                raise StudioQuestError("authored revision request exceeds byte budget")
            def unique(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise StudioQuestError("duplicate authored revision JSON key")
                    obj[key] = value
                return obj
            request = json.loads(
                encoded, object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    StudioQuestError("nonfinite authored revision JSON")),
            )
            original = (load_revision_bundle(args.revision_source, authorized=True,
                                              project_id=args.project)[0]
                        if args.revision_source is not None
                        else read_blueprint(args.project))
            source, html, receipt = preview_canon_revision(
                original, request, authorized=True,
            )
            write_revision_bundle(args.output, source, html, receipt)
        except (StudioQuestError, ValueError, TypeError, UnicodeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps({"receipt": receipt, "output": str(args.output)},
                         sort_keys=True, separators=(",", ":")))
        return 0
    if args.revision_request is not None:
        ap.error("--revision-request requires --author-revision")
    if args.revision_source is not None and not (args.audit_canon or args.play_walk):
        ap.error("--revision-source requires --author-revision, --audit-canon or --play-walk")
    if args.audit_canon:
        if (not args.project or args.play_walk or args.play_quest
                or args.walk_audit_catalog or args.walk_audit_aggregate_stdin
                or args.compile_preview or args.materialize_batch or args.output
                or args.search is not None or args.deep_search or args.genre or args.biome
                or args.limit != 20 or args.quest_actions is not None
                or args.max_artifact_bytes is not None):
            ap.error("--audit-canon requires --project and excludes other modes")
        from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
        from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
        try:
            if args.revision_source is not None:
                from skeleton.ai.game_builder.studio_ecosystem_author_revision import load_revision_bundle
                docs = load_revision_bundle(args.revision_source, authorized=True,
                                            project_id=args.project)[0]
            else:
                docs = read_blueprint(args.project)
            proof = audit_canon_source(docs, authorized=True)
        except (StudioQuestError, ValueError, TypeError, OSError) as exc:
            ap.error(str(exc))
        print(json.dumps(proof, sort_keys=True, separators=(",", ":")))
        return 0
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
            if args.revision_source is not None:
                from skeleton.ai.game_builder.studio_ecosystem_author_revision import load_revision_bundle
                docs = load_revision_bundle(args.revision_source, authorized=True,
                                            project_id=args.project)[0]
            else:
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
            elif args.walk_canon_journal:
                from skeleton.ai.game_builder.studio_ecosystem_walk_canon_journal import walk_canon_journal
                print(json.dumps({"receipt": json.loads(receipt),
                                  "canon_journal": walk_canon_journal(
                                      session, docs, authorized=True,
                                      offset=args.walk_journal_offset,
                                      limit=args.walk_journal_limit,
                                      expected_session_digest=args.walk_journal_expected_session_digest,
                                      expected_source_digest=args.walk_journal_expected_source_digest)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_story_transcript:
                from skeleton.ai.game_builder.studio_ecosystem_walk_story_transcript import walk_story_transcript
                print(json.dumps({"receipt": json.loads(receipt),
                                  "story_transcript": walk_story_transcript(
                                      session, docs, authorized=True,
                                      offset=args.walk_story_offset,
                                      max_scenes=args.walk_story_limit,
                                      expected_session_digest=args.walk_story_expected_digest)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_timeline:
                print(json.dumps({"receipt": json.loads(receipt),
                                  "timeline": walk_checkpoint_timeline(
                                      session, docs, authorized=True)},
                                 sort_keys=True, separators=(",", ":")))
            elif args.walk_audit_choices:
                from skeleton.ai.game_builder.studio_ecosystem_walk_coverage import (
                    audit_walk_choice_coverage,
                )
                print(json.dumps({"receipt": json.loads(receipt),
                                  "choice_coverage": audit_walk_choice_coverage(
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
                  and not args.walk_timeline and not args.walk_story_transcript
                  and not args.walk_canon_journal
                  and not args.walk_audit_choices
                  and args.walk_restore_checkpoint is None):
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
