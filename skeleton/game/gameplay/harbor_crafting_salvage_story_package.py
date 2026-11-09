"""Portable original story mission package with full source-to-event replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage import build_salvage
from .harbor_crafting_salvage_quest_events import (
    MAX_STORY_REPORT_BYTES, build_salvage_story, validate_story_board,
    verify_salvage_story,
)

SCHEMA = "skeleton.game.harbor.salvage-story-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.salvage-story-play.v1"
MAX_PACKAGE_BYTES = 262144
MAX_PLAY_BYTES = MAX_STORY_REPORT_BYTES * 2
PACKAGE_KEYS = {"schema", "id", "source", "salvage_board", "story_board",
                "source_digest", "story_board_digest", "package_digest"}
PLAY_KEYS = {"schema", "package", "story", "play_digest"}


def build_story_package(source: Any, salvage_board: Any, story_board: Any, *,
                        package_id: str) -> dict[str, Any]:
    initial = build_salvage(source, salvage_board, [])
    authored = validate_story_board(story_board, initial)
    result = {"schema": SCHEMA, "id": _identifier(package_id, "story package id"),
              "source": initial["source"], "salvage_board": initial["board"],
              "story_board": authored, "source_digest": initial["source_digest"],
              "story_board_digest": digest(authored)}
    result["package_digest"] = digest(result)
    if len(canonical(result)) > MAX_PACKAGE_BYTES:
        raise HarborError("salvage story package oversized")
    return result


def verify_story_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_KEYS, "salvage story package")
    if package["schema"] != SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized salvage story package")
    rebuilt = build_story_package(
        package["source"], package["salvage_board"], package["story_board"],
        package_id=package["id"],
    )
    if rebuilt != package:
        raise HarborError("salvage story package replay mismatch")
    return deepcopy(package)


def play_story_package(package: Any, actions: Any, *,
                       require_all: bool = False) -> dict[str, Any]:
    authored = verify_story_package(package)
    report = build_salvage(authored["source"], authored["salvage_board"], actions,
                           require_complete=require_all)
    story = build_salvage_story(report, authored["story_board"], require_all=require_all)
    result = {"schema": PLAY_SCHEMA, "package": authored, "story": story}
    result["play_digest"] = digest(result)
    if len(canonical(result)) > MAX_PLAY_BYTES:
        raise HarborError("salvage story package play oversized")
    return result


def verify_story_package_play(play: Any, *,
                              require_all: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_KEYS, "salvage story play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized salvage story play")
    if play["play_digest"] != digest({k: v for k, v in play.items()
                                      if k != "play_digest"}):
        raise HarborError("salvage story play digest mismatch")
    package = verify_story_package(play["package"])
    status = verify_salvage_story(play["story"], require_all=require_all)
    rebuilt = play_story_package(package, play["story"]["report"]["actions"],
                                 require_all=require_all)
    if rebuilt != play:
        raise HarborError("salvage story package play replay mismatch")
    return status
