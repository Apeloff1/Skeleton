"""Private CLI for original story bookmarks, restore and static HTML review."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from skeleton.ai.agents.jeeves.studio_story_reading_bookmark_tool import (
    REQUEST_SCHEMA, execute_story_reading_bookmark_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_story_reading_bookmark import (
    replay_story_reading_bookmark, render_story_reading_bookmark_html,
)
from skeleton.ai.game_builder.studio_story_checkpoint_cli import _read_private_checkpoint
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import (
    _basename, _publish_private,
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StudioQuestError("duplicate story bookmark JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise StudioQuestError("nonfinite story bookmark JSON number")


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_story_reading_bookmark_cli",
        description="Save or restore source-bound original story reader position",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    mode = entry.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request-file", help="Owner-private JSON stage and note")
    mode.add_argument("--restore-file", help="Owner-private existing bookmark receipt")
    entry.add_argument("--format", choices=("json", "html"), required=True)
    entry.add_argument("--output-file", required=True)
    entry.add_argument("--trusted-local-operator", action="store_true")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: operator authorization required", file=sys.stderr)
        return 2
    try:
        input_file = _basename(args.request_file or args.restore_file)
        output_file = _basename(args.output_file)
        if input_file == output_file:
            raise StudioQuestError("bookmark input and output must differ")
        suffix = ".json" if args.format == "json" else ".html"
        if not output_file.endswith(suffix):
            raise StudioQuestError("bookmark output extension differs from format")
        raw = _read_private_checkpoint(input_file)
        data = json.loads(raw, object_pairs_hook=_unique,
                          parse_constant=_reject_constant)
        if args.restore_file is not None:
            if args.format != "html":
                raise StudioQuestError("restored bookmark can only produce HTML review")
            docs = read_blueprint(args.project_id)
            receipt = replay_story_reading_bookmark(
                docs, data, authorized=True,
                expected_source_digest=args.quest_source_digest)
            content = render_story_reading_bookmark_html(
                docs, receipt, authorized=True,
                expected_source_digest=args.quest_source_digest).decode("utf-8")
            digest = receipt["bookmark_digest"]
        else:
            if type(data) is not dict or set(data) != {"stage_id", "reader_note"}:
                raise StudioQuestError("bookmark input requires exact stage and note")
            result = execute_story_reading_bookmark_tool({
                "schema": REQUEST_SCHEMA, "project_id": args.project_id,
                "expected_quest_source_digest": args.quest_source_digest,
                "stage_id": data["stage_id"], "reader_note": data["reader_note"],
                "format": args.format,
            }, authorized=True)
            content = result["content"]
            digest = result["bookmark_digest"]
        _publish_private(output_file, content)
    except (StudioQuestError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "schema": "skeleton.game_builder.story_reading_bookmark_cli_receipt.v1",
        "project_id": args.project_id,
        "source_digest": args.quest_source_digest,
        "bookmark_digest": digest, "format": args.format,
        "saved_new_private_file": True, "quest_action_committed": False,
        "release_certified": False,
    }, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
