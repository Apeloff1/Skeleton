"""Portable replay-verified earned championship ending and epilogue package."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_season_choices import (
    MAX_REPORT_BYTES, build_season_choice, verify_season_choice,
    validate_season_choices,
)
from .harbor_crafting_salvage_season import verify_salvage_season

SCHEMA = "skeleton.game.harbor.salvage-season-choice-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.salvage-season-choice-play.v1"
MAX_PACKAGE_BYTES = MAX_REPORT_BYTES
MAX_PLAY_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {"schema", "id", "save", "board", "package_digest"}
PLAY_FIELDS = {"schema", "package", "report", "play_digest"}


def build_choice_package(save: Any, board: Any, *, package_id: str) -> dict[str, Any]:
    verify_salvage_season(save, require_complete=True)
    authored = validate_season_choices(board, save)
    result = {"schema": SCHEMA, "id": _identifier(package_id, "choice package id"),
              "save": deepcopy(save), "board": authored}
    result["package_digest"] = digest(result)
    if len(canonical(result)) > MAX_PACKAGE_BYTES:
        raise HarborError("salvage choice package oversized")
    return result


def verify_choice_package(package: Any) -> dict[str, Any]:
    _keys(package, FIELDS, "salvage choice package")
    if package["schema"] != SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized salvage choice package")
    rebuilt = build_choice_package(package["save"], package["board"],
                                   package_id=package["id"])
    if rebuilt != package:
        raise HarborError("salvage choice package replay mismatch")
    return deepcopy(package)


def play_choice_package(package: Any, choice_id: str) -> dict[str, Any]:
    authored = verify_choice_package(package)
    report = build_season_choice(authored["save"], authored["board"], choice_id)
    result = {"schema": PLAY_SCHEMA, "package": authored, "report": report}
    result["play_digest"] = digest(result)
    if len(canonical(result)) > MAX_PLAY_BYTES:
        raise HarborError("salvage choice play oversized")
    return result


def verify_choice_package_play(play: Any) -> dict[str, Any]:
    _keys(play, PLAY_FIELDS, "salvage choice play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized salvage choice play")
    if play["play_digest"] != digest({k: v for k, v in play.items()
                                      if k != "play_digest"}):
        raise HarborError("salvage choice play digest mismatch")
    package = verify_choice_package(play["package"])
    outcome = verify_season_choice(play["report"])
    rebuilt = play_choice_package(package, play["report"]["choice"])
    if rebuilt != play:
        raise HarborError("salvage choice package play replay mismatch")
    return deepcopy(outcome)
