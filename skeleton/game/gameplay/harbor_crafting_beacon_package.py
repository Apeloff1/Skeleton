"""Portable source-bound beacon rescue game package and playable session."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_beacons import (
    MAX_REPORT_BYTES, build_beacon_rescue, resume_beacon_rescue,
    validate_beacon_board, verify_beacon_rescue,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.beacon-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.beacon-play.v1"
MAX_PACKAGE_BYTES = 131072
MAX_PLAY_BYTES = MAX_REPORT_BYTES + MAX_PACKAGE_BYTES + 8192


def build_beacon_package(identifier: str, source: Any, board: Any) -> dict[str, Any]:
    package = {
        "schema": PACKAGE_SCHEMA, "id": _identifier(identifier, "beacon package id"),
        "source": validate_source(source),
        "board": validate_beacon_board(board, source),
    }
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("beacon package exceeds byte budget")
    return package


def verify_beacon_package(package: Any) -> dict[str, Any]:
    _keys(package, {"schema", "id", "source", "board", "package_digest"}, "beacon package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized beacon package")
    rebuilt = build_beacon_package(package["id"], package["source"], package["board"])
    if rebuilt != package:
        raise HarborError("beacon package replay mismatch")
    return {"verified": True, "package_digest": rebuilt["package_digest"]}


def play_beacon_package(package: Any, actions: Any, *,
                        require_rescue: bool = False) -> dict[str, Any]:
    verify_beacon_package(package)
    report = build_beacon_rescue(
        package["source"], package["board"], actions, require_rescue=require_rescue,
    )
    play = {"schema": PLAY_SCHEMA, "package": deepcopy(package), "report": report}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("beacon package play exceeds byte budget")
    return play


def verify_beacon_package_play(play: Any, *,
                               require_rescue: bool = False) -> dict[str, Any]:
    _keys(play, {"schema", "package", "report", "play_digest"}, "beacon play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized beacon play")
    verify_beacon_package(play["package"])
    verify_beacon_rescue(play["report"], require_rescue=require_rescue)
    rebuilt = play_beacon_package(
        play["package"], play["report"]["actions"], require_rescue=require_rescue,
    )
    if rebuilt != play:
        raise HarborError("beacon package play replay mismatch")
    return {
        "verified": True, "rescued": rebuilt["report"]["state"]["rescued"],
        "play_digest": rebuilt["play_digest"],
    }


def resume_beacon_package(play: Any, actions: Any, *, expected_digest: str,
                          require_rescue: bool = False) -> dict[str, Any]:
    verify_beacon_package_play(play)
    if type(expected_digest) is not str or expected_digest != play["play_digest"]:
        raise HarborError("stale beacon package lease")
    advanced = resume_beacon_rescue(
        play["report"], actions, expected_digest=play["report"]["report_digest"],
        require_rescue=require_rescue,
    )
    rebuilt = play_beacon_package(
        play["package"], advanced["actions"], require_rescue=require_rescue,
    )
    if rebuilt["report"] != advanced:
        raise HarborError("beacon package continuation mismatch")
    return rebuilt
