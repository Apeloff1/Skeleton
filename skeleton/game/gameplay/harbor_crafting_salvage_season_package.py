"""Portable original salvage championship package and replay-verified play."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_season import (
    MAX_SEASON_BOARD_BYTES, MAX_SEASON_SAVE_BYTES,
    append_salvage_round, start_salvage_season, validate_salvage_season,
    verify_salvage_season,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.salvage-season-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.salvage-season-play.v1"
MAX_PACKAGE_BYTES = MAX_SEASON_BOARD_BYTES * 2
MAX_PLAY_BYTES = MAX_SEASON_SAVE_BYTES * 2
PACKAGE_KEYS = {"schema", "id", "source", "board", "source_digest",
                "board_digest", "package_digest"}
PLAY_KEYS = {"schema", "package", "save", "package_digest", "play_digest"}


def build_season_package(source: Any, board: Any, *, package_id: str) -> dict[str, Any]:
    authored = validate_salvage_season(board, source)
    world = start_salvage_season(source, authored)["source"]
    result = {"schema": PACKAGE_SCHEMA, "id": _identifier(package_id, "season package id"),
              "source": world, "board": authored,
              "source_digest": digest(world), "board_digest": digest(authored)}
    result["package_digest"] = digest(result)
    if len(canonical(result)) > MAX_PACKAGE_BYTES:
        raise HarborError("salvage season package oversized")
    return result


def verify_season_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_KEYS, "salvage season package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("invalid salvage season package")
    rebuilt = build_season_package(package["source"], package["board"],
                                   package_id=package["id"])
    if rebuilt != package:
        raise HarborError("salvage season package digest mismatch")
    return deepcopy(package)


def play_season_package(package: Any, rounds: Any, *,
                        require_complete: bool = False) -> dict[str, Any]:
    authored = verify_season_package(package)
    if not isinstance(rounds, list) or len(rounds) > len(authored["board"]["rounds"]):
        raise HarborError("salvage season package round budget exceeded")
    save = start_salvage_season(authored["source"], authored["board"])
    for actions in rounds:
        save = append_salvage_round(save, actions, expected_tip=save["tip"])
    verify_salvage_season(save, require_complete=require_complete)
    result = {"schema": PLAY_SCHEMA, "package": authored, "save": save,
              "package_digest": authored["package_digest"]}
    result["play_digest"] = digest(result)
    if len(canonical(result)) > MAX_PLAY_BYTES:
        raise HarborError("salvage season play oversized")
    return result


def verify_season_package_play(play: Any, *,
                               require_complete: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_KEYS, "salvage season play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("invalid salvage season play")
    if play["play_digest"] != digest({k: v for k, v in play.items()
                                      if k != "play_digest"}):
        raise HarborError("salvage season play digest mismatch")
    package = verify_season_package(play["package"])
    status = verify_salvage_season(play["save"], require_complete=require_complete)
    actions = [report["actions"] for report in play["save"]["reports"]]
    rebuilt = play_season_package(package, actions, require_complete=require_complete)
    if rebuilt != play or play["package_digest"] != package["package_digest"]:
        raise HarborError("salvage season package replay mismatch")
    return status
