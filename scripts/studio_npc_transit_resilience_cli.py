"""CLI for typed route disruption rehearsals, custody and playable fallback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience import (
    PROMPT, compile_npc_transit_resilience, propose_npc_transit_resilience,
    restore_npc_transit_resilience, publish_npc_transit_resilience,
    select_npc_transit_fallback,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound NPC route disruption audit")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--baseline-transit")
    ap.add_argument("--prompt", action="store_true")
    ap.add_argument("--variants")
    ap.add_argument("--import-variants", type=Path)
    ap.add_argument("--baseline-resilience")
    ap.add_argument("--editor-directory", type=Path)
    ap.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--select")
    ap.add_argument("--playable-manifest", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None:
        if (args.baseline_transit is not None or args.prompt or args.variants is not None
                or args.import_variants is not None or args.baseline_resilience is not None):
            ap.error("restore cannot be combined with new authoring")
    elif (args.baseline_transit is None or
          sum((args.prompt, args.variants is not None, args.import_variants is not None)) != 1):
        ap.error("supply baseline transit and exactly one prompt or variants")
    if args.playable_manifest and not args.select:
        ap.error("playable handoff requires a selected variant")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            result = restore_npc_transit_resilience(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            baseline = _strict(args.baseline_transit, max_bytes=262144)
            if type(baseline) is not dict or baseline.get("source_digest") != args.expected_source:
                raise StudioQuestError("stale NPC resilience source lease")
            if args.prompt:
                result = propose_npc_transit_resilience(
                    docs, baseline, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.import_variants is not None:
                    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience import (
                        replay_npc_transit_resilience,
                    )
                    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience_editor import (
                        load_npc_resilience_editor_export,
                    )
                    if args.baseline_resilience is None:
                        raise StudioQuestError("NPC disruption import requires original receipt")
                    original = replay_npc_transit_resilience(
                        docs, _strict(args.baseline_resilience, max_bytes=524288),
                        authorized=True)
                    if (original["baseline_receipt"] != baseline
                            or original["source_digest"] != args.expected_source):
                        raise StudioQuestError("stale NPC disruption editor baseline")
                    variants = load_npc_resilience_editor_export(
                        args.import_variants, authorized=True,
                        expected_project_id=original["project_id"],
                        expected_source_digest=original["source_digest"],
                        expected_session_digest=original["session_digest"],
                        expected_temporal_digest=original["temporal_digest"],
                        expected_transit_digest=original["baseline_transit_digest"],
                        expected_resilience_digest=original["resilience_digest"])
                else:
                    if args.baseline_resilience is not None:
                        raise StudioQuestError("baseline receipt only valid with import")
                    variants = _strict(args.variants, max_bytes=32768)
                result = compile_npc_transit_resilience(
                    docs, baseline, variants,
                    authorized=True, expected_source_digest=args.expected_source)
        output = {"resilience": result}
        if args.editor_directory:
            from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience_editor import (
                publish_npc_resilience_editor,
            )
            output["editor"] = publish_npc_resilience_editor(
                docs, result, args.editor_directory, authorized=True)
        if args.select:
            output["selection"] = select_npc_transit_fallback(
                docs, result, args.select, authorized=True,
                playable=args.playable_manifest)
        if args.publish:
            output["publication"] = publish_npc_transit_resilience(
                docs, result, args.publish, authorized=True)
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
