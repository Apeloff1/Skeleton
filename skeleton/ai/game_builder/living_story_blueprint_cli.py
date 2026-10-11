"""Offline original living-world blueprint maker for human story authors."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .living_story_runtime import StoryError, original_story_world
from .living_story_authoring import (
    StoryAuthoringError, derive_original_story_intent, blueprint_document,
    compile_authored_story, MAX_DOCUMENT_BYTES,
)
from .playable_cli import _intent, _read_json, MAX_INPUT_BYTES
from .playable_world import PlayableWorldError
from .contracts import canonical_json


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.living_story_blueprint_cli",
        description="Create an original offline editable NPC, region, schedule and quest blueprint.",
    )
    p.add_argument("--intent", required=True, help="Existing original game-build intent JSON")
    p.add_argument("--output", required=True, help="New JSON blueprint destination; never overwrite")
    p.add_argument("--npcs", type=int, default=24, help="Actual NPCs, 6 to 128")
    p.add_argument("--regions", type=int, default=7, help="Original connected regions, 4 to 12")
    p.add_argument("--mode", choices=("campaign", "postgame", "sandbox"),
                   default="postgame", help="Story ending behavior")
    p.add_argument("--quests", type=int, default=2, help="Quests needed for ending, 1-3")
    p.add_argument("--trusted-local-operator", action="store_true",
                   help="Confirm operator authority before generating authoring files")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: operator approval acknowledgement required", file=sys.stderr)
        return 2
    try:
        parent = _intent(_read_json(args.intent, MAX_INPUT_BYTES))
        story_intent = derive_original_story_intent(
            parent, population=args.npcs, regions=args.regions,
            mode=args.mode, quests=args.quests, authorized=True,
        )
        world = original_story_world(story_intent, authorized=True)
        blueprint = blueprint_document(world, authorized=True)
        approved = compile_authored_story(
            story_intent, blueprint, authorized=True, human_reviewed=True,
        )
        data = (canonical_json(blueprint) + "\n").encode("utf-8")
        if len(data) > MAX_DOCUMENT_BYTES:
            raise StoryAuthoringError("authored NPC template exceeds JSON byte limit")
        destination = Path(args.output)
        if (destination.suffix.lower() != ".json"
                or destination.exists() or destination.is_symlink()
                or not destination.parent.is_dir() or destination.parent.is_symlink()):
            raise StoryAuthoringError("new .json destination in real existing directory required")
        with destination.open("xb") as handle:
            handle.write(data)
        print(canonical_json({
            "schema": "skeleton.game_builder.living_story_template_result.v1",
            "source": str(destination),
            "world_digest": approved.world.digest,
            "proof_digest": approved.proof_digest,
            "npcs": len(world.citizens),
            "regions": len(world.regions),
            "original_authoring_review_required_before_consumer_export": True,
            "next_step": "original_game_studio_cli --living-world-blueprint --living-world-human-reviewed",
        }))
        return 0
    except (StoryAuthoringError, StoryError, PlayableWorldError, OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "parser"]
