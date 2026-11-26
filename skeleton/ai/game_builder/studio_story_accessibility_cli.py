"""Private, no-overwrite CLI for original accessible story reading editions."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from skeleton.ai.agents.jeeves.studio_story_accessibility_tool import (
    REQUEST_SCHEMA, execute_story_accessibility_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import (
    _basename, _publish_private,
)


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_story_accessibility_cli",
        description="Compile original authored story to a private accessible reading edition",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    entry.add_argument("--format", choices=("markdown", "webvtt"), required=True)
    entry.add_argument("--output-file", required=True)
    entry.add_argument("--trusted-local-operator", action="store_true")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authorization required", file=sys.stderr)
        return 2
    try:
        name = _basename(args.output_file)
        expected_extension = ".md" if args.format == "markdown" else ".vtt"
        if not name.endswith(expected_extension):
            raise StudioQuestError("accessibility output extension does not match format")
        result = execute_story_accessibility_tool({
            "schema": REQUEST_SCHEMA,
            "project_id": args.project_id,
            "expected_quest_source_digest": args.quest_source_digest,
            "format": args.format,
        }, authorized=True)
        _publish_private(name, result["content"])
    except (StudioQuestError, OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "schema": "skeleton.game_builder.story_accessibility_cli_receipt.v1",
        "project_id": args.project_id,
        "format": args.format,
        "source_digest": args.quest_source_digest,
        "content_sha256": result["content_sha256"],
        "saved_new_private_file": True,
        "audio_rendered": False,
        "release_certified": False,
    }, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
