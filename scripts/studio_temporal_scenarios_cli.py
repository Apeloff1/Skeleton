"""Operator CLI for source-bound timeline what-if revisions and playable handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios_editor import (
    load_temporal_scenarios_editor_export, publish_temporal_scenarios_editor,
)
from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios import (
    PROMPT, compile_temporal_scenarios, propose_temporal_scenarios,
    publish_temporal_scenarios, restore_temporal_scenarios,
    select_temporal_scenario,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-leased temporal what-if planner")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]")
    ap.add_argument("--baseline-authoring")
    ap.add_argument("--prompt", action="store_true")
    ap.add_argument("--candidates")
    ap.add_argument("--import-candidates", type=Path)
    ap.add_argument("--baseline-scenarios")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--select")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None:
        if (args.prompt or args.candidates is not None or args.baseline_authoring is not None
                or args.import_candidates is not None or args.baseline_scenarios is not None):
            ap.error("restore cannot be combined with scenario generation")
    elif (args.baseline_authoring is None or
          (sum((args.prompt, args.candidates is not None,
                args.import_candidates is not None)) != 1)):
        ap.error("supply baseline and exactly one of --prompt or --candidates")
    if args.playable_manifest and not args.select:
        ap.error("playable manifest requires --select")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            receipt = restore_temporal_scenarios(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if (args.expected_session is not None and
                    receipt["session_digest"] != args.expected_session):
                raise StudioQuestError("stale restored scenario session")
        else:
            actions = _strict(args.actions, max_bytes=16384)
            baseline = _strict(args.baseline_authoring, max_bytes=32768)
            if args.prompt:
                receipt = propose_temporal_scenarios(
                    docs, actions, baseline, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=args.expected_session)
            else:
                if args.import_candidates is not None:
                    from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios import (
                        replay_temporal_scenarios,
                    )
                    if args.baseline_scenarios is None:
                        raise StudioQuestError("scenario import requires original receipt")
                    original = replay_temporal_scenarios(
                        docs, _strict(args.baseline_scenarios, max_bytes=262144),
                        authorized=True)
                    if (original["baseline_authoring"] != baseline
                            or original["actions"] != actions
                            or original["source_digest"] != args.expected_source
                            or (args.expected_session is not None
                                and original["session_digest"] != args.expected_session)):
                        raise StudioQuestError("stale temporal scenario import baseline")
                    candidates = load_temporal_scenarios_editor_export(
                        args.import_candidates, authorized=True,
                        expected_project_id=original["project_id"],
                        expected_source_digest=original["source_digest"],
                        expected_session_digest=original["session_digest"],
                        expected_baseline_digest=original["scenario_digest"])
                else:
                    if args.baseline_scenarios is not None:
                        raise StudioQuestError("original scenario receipt only valid with import")
                    candidates = _strict(args.candidates, max_bytes=65536)
                receipt = compile_temporal_scenarios(
                    docs, actions, baseline, candidates, authorized=True,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=args.expected_session)
        result = {"scenarios": receipt}
        if args.editor_directory:
            result["editor"] = publish_temporal_scenarios_editor(
                docs, receipt, args.editor_directory, authorized=True)
        if args.select:
            result["selection"] = select_temporal_scenario(
                docs, receipt, args.select, authorized=True,
                playable=args.playable_manifest)
        if args.publish:
            result["publication"] = publish_temporal_scenarios(
                docs, receipt, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
