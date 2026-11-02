"""Source-only scene label proposal CLI; emits private editable request JSON."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from skeleton.ai.agents.jeeves.studio_scene_object_accessibility_tool import (
    PROPOSAL_REQUEST_SCHEMA, execute_scene_object_accessibility_proposal_tool,
)
from skeleton.ai.game_builder.studio_scene_object_accessibility import PROPOSAL_PROMPT
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import (
    _basename, _publish_private,
)


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_scene_object_accessibility_proposal_cli",
        description="Propose editable original scene labels without inventing art evidence",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    entry.add_argument("--scene-id", required=True)
    entry.add_argument("--prompt", required=True)
    entry.add_argument("--output-file", required=True)
    entry.add_argument("--trusted-local-operator", action="store_true")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: operator authorization required", file=sys.stderr)
        return 2
    try:
        name = _basename(args.output_file)
        if not name.endswith(".json"):
            raise StudioQuestError("proposal must be saved as JSON")
        if args.prompt != PROPOSAL_PROMPT:
            raise StudioQuestError("unsupported source-only scene proposal prompt")
        result = execute_scene_object_accessibility_proposal_tool({
            "schema": PROPOSAL_REQUEST_SCHEMA, "project_id": args.project_id,
            "expected_quest_source_digest": args.quest_source_digest,
            "scene_id": args.scene_id, "prompt": args.prompt,
        }, authorized=True)
        _publish_private(name, _canonical(result["proposal"]).decode("ascii") + "\n")
    except (StudioQuestError, OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "schema": "skeleton.game_builder.scene_accessibility_proposal_cli_receipt.v1",
        "project_id": args.project_id,
        "source_digest": args.quest_source_digest,
        "proposal_digest": result["proposal_digest"],
        "saved_new_private_file": True,
        "visual_appearance_verified": False, "release_certified": False,
    }, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
