"""Verify offline browser-authored choices against the canonical original quest.

The browser export is an edit request, not a trusted game save. This command
replays its entire history and prints a deterministic source-bound receipt.
It does not write canonical source or grant itself game release authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_director_choice_rehearsal import (
    load_choice_export, replay_choice_export,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a source-bound offline director quest-choice export")
    parser.add_argument("--project", required=True, help="Registered original studio project")
    parser.add_argument("--expected-source", required=True,
                        help="Canonical source digest from the playable director manifest")
    parser.add_argument("--expected-session", required=True,
                        help="Baseline quest-session digest from the director manifest")
    parser.add_argument("--export", type=Path, required=True,
                        help="Existing studio_choice_rehearsal.json from the offline editor")
    args = parser.parse_args(argv)
    try:
        documents = read_blueprint(args.project)
        export = load_choice_export(args.export)
        result = replay_choice_export(
            documents, export, authorized=True,
            expected_source_digest=args.expected_source,
            expected_session_digest=args.expected_session)
        if result["project_id"] != args.project:
            raise StudioQuestError("choice export project mismatch")
    except (StudioQuestError, OSError, ValueError, TypeError, PermissionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
