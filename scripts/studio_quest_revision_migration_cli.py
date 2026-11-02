"""Offline operator CLI for source-leased authored quest save migration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_revision_migration import (
    compile_quest_revision_migration, replay_quest_revision_migration,
    compile_quest_migration_handoff, publish_quest_revision_migration,
    restore_quest_revision_migration,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Migrate original quest save only through reviewed authored revision")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan-file", type=Path)
    modes.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--handoff", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and args.publish:
        ap.error("restore cannot publish")
    try:
        docs = read_blueprint(args.project)
        if args.restore:
            report = restore_quest_revision_migration(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
            if report["initial_session_digest"] != args.expected_session:
                raise StudioQuestError("stale migration initial session")
        else:
            report = compile_quest_revision_migration(
                docs, _private_json(args.plan_file, 32768), authorized=True,
                expected_source_digest=args.expected_source,
                expected_initial_session_digest=args.expected_session)
        replay_quest_revision_migration(docs, report, authorized=True)
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_quest_revision_migration.v1",
            "migration": report, "file_write_performed": False,
            "release_certified": False,
        }
        if args.handoff:
            result["playable_handoff"] = compile_quest_migration_handoff(
                docs, report, authorized=True)
        if args.publish:
            result["publication"] = publish_quest_revision_migration(
                docs, report, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
