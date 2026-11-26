"""Operator prompt→quest proof→real catalog HTML5 playable→private ZIP."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_readiness_editor import (
    import_quest_readiness_editor_export,
)
from skeleton.ai.game_builder.studio_quest_readiness import (
    PROMPT, compile_quest_readiness, propose_quest_readiness,
    restore_quest_readiness,
)
from skeleton.ai.game_builder.studio_quest_readiness_playable import (
    compile_quest_readiness_playable, publish_quest_readiness_playable,
    verify_quest_readiness_playable,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Source-bound canonical quest readiness to real HTML5 playable")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prompt", action="store_true")
    modes.add_argument("--budget-file", type=Path)
    modes.add_argument("--restore-proof", type=Path)
    modes.add_argument("--editor-export", type=Path)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--publish", type=Path)
    output.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    try:
        docs = read_blueprint(args.project)
        leases = {
            "authorized": True,
            "expected_source_digest": args.expected_source,
            "expected_initial_session_digest": args.expected_session,
        }
        if args.restore_proof:
            readiness = restore_quest_readiness(
                docs, args.restore_proof, authorized=True,
                expected_source_digest=args.expected_source)
            if readiness["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored readiness session")
        elif args.editor_export:
            readiness = import_quest_readiness_editor_export(
                docs, args.editor_export, **leases)
        elif args.prompt:
            readiness = propose_quest_readiness(docs, PROMPT, **leases)
        else:
            readiness = compile_quest_readiness(
                docs, _private_json(args.budget_file, 32768), **leases)
        manifest, bundle = compile_quest_readiness_playable(
            docs, readiness, authorized=True)
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_readiness_playable.v1",
            "manifest": manifest, "file_write_performed": False,
            "release_certified": False,
        }
        if args.publish:
            result["publication"] = publish_quest_readiness_playable(
                docs, readiness, manifest, bundle, args.publish, authorized=True)
            result["file_write_performed"] = True
        if args.verify:
            if verify_quest_readiness_playable(
                    docs, readiness, args.verify, authorized=True) != manifest:
                raise StudioQuestError("readiness playable verification mismatch")
            result["verified_existing_bundle"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
