"""Private source-leased CLI for original scene object accessibility labels."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from skeleton.ai.agents.jeeves.studio_scene_object_accessibility_tool import (
    REQUEST_SCHEMA, execute_scene_object_accessibility_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_scene_object_accessibility import (
    REQUEST_SCHEMA as SOURCE_REQUEST_SCHEMA,
    replay_scene_object_accessibility, render_scene_object_accessibility_html,
)
from skeleton.ai.game_builder.studio_story_checkpoint_cli import _read_private_checkpoint
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import (
    _basename, _publish_private,
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise StudioQuestError("duplicate scene accessibility JSON key")
        output[key] = value
    return output


def _invalid_constant(_: str) -> None:
    raise StudioQuestError("nonfinite scene accessibility JSON number")


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_scene_object_accessibility_cli",
        description="Save or replay original source-bound scene accessibility labels",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    mode = entry.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request-file", help="Private scene ID and label map")
    mode.add_argument("--restore-file", help="Private existing canonical label receipt")
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
            raise StudioQuestError("scene label input and output must differ")
        suffix = ".json" if args.format == "json" else ".html"
        if not output_file.endswith(suffix):
            raise StudioQuestError("scene label output extension differs from format")
        raw = _read_private_checkpoint(input_file)
        data = json.loads(raw, object_pairs_hook=_unique,
                          parse_constant=_invalid_constant)
        if args.restore_file is not None:
            if args.format != "html":
                raise StudioQuestError("restored scene labels only produce HTML review")
            docs = read_blueprint(args.project_id)
            receipt = replay_scene_object_accessibility(
                docs, data, authorized=True,
                expected_source_digest=args.quest_source_digest)
            content = render_scene_object_accessibility_html(
                docs, receipt, authorized=True,
                expected_source_digest=args.quest_source_digest).decode("utf-8")
            digest = receipt["accessibility_digest"]
        else:
            if (type(data) is not dict or set(data) not in (
                    {"scene_id", "labels"}, {"schema", "scene_id", "labels"})):
                raise StudioQuestError("scene label input requires exact fields")
            if "schema" in data and data["schema"] != SOURCE_REQUEST_SCHEMA:
                raise StudioQuestError("unsupported scene label proposal schema")
            result = execute_scene_object_accessibility_tool({
                "schema": REQUEST_SCHEMA, "project_id": args.project_id,
                "expected_quest_source_digest": args.quest_source_digest,
                "scene_id": data["scene_id"], "labels": data["labels"],
                "format": args.format,
            }, authorized=True)
            content = result["content"]
            digest = result["accessibility_digest"]
        _publish_private(output_file, content)
    except (StudioQuestError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "schema": "skeleton.game_builder.scene_object_accessibility_cli_receipt.v1",
        "project_id": args.project_id,
        "source_digest": args.quest_source_digest,
        "accessibility_digest": digest, "format": args.format,
        "saved_new_private_file": True, "asset_rendered": False,
        "accessibility_device_verified": False, "release_certified": False,
    }, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
