"""Owner-private CLI for original-story caption timing edits and review."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from skeleton.ai.agents.jeeves.studio_caption_timing_tool import (
    REQUEST_SCHEMA, execute_caption_timing_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_story_checkpoint_cli import _read_private_checkpoint
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import (
    _basename, _publish_private,
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise StudioQuestError("duplicate caption timing JSON key")
        output[key] = value
    return output


def _invalid_constant(_: str) -> None:
    raise StudioQuestError("nonfinite caption timing JSON number")


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_caption_timing_cli",
        description="Compile source-leased synthetic caption timing edits privately",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    entry.add_argument("--edits-file", required=True,
                       help="Owner-private JSON mapping of 1-based cue indexes to milliseconds")
    entry.add_argument("--format", required=True, choices=("webvtt", "html"))
    entry.add_argument("--output-file", required=True)
    entry.add_argument("--trusted-local-operator", action="store_true")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: operator authorization required", file=sys.stderr)
        return 2
    try:
        edits_file = _basename(args.edits_file)
        output_file = _basename(args.output_file)
        if edits_file == output_file:
            raise StudioQuestError("caption edit input and output must differ")
        suffix = ".vtt" if args.format == "webvtt" else ".html"
        if not output_file.endswith(suffix):
            raise StudioQuestError("caption output extension differs from format")
        raw = _read_private_checkpoint(edits_file)
        if len(raw.encode("utf-8")) > 4096:
            raise StudioQuestError("caption timing edit input exceeds byte budget")
        edits = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=_invalid_constant)
        result = execute_caption_timing_tool({
            "schema": REQUEST_SCHEMA, "project_id": args.project_id,
            "expected_quest_source_digest": args.quest_source_digest,
            "edits_ms": edits, "format": args.format,
        }, authorized=True)
        _publish_private(output_file, result["content"])
    except (StudioQuestError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "schema": "skeleton.game_builder.caption_timing_cli_receipt.v1",
        "project_id": args.project_id, "source_digest": args.quest_source_digest,
        "format": args.format, "content_sha256": result["content_sha256"],
        "edit_digest": result["edit_digest"],
        "operator_changed_count": result["operator_changed_count"],
        "saved_new_private_file": True,
        "audio_sync_verified": False, "release_certified": False,
    }, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
