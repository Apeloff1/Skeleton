"""Portable original convoy game package with independently replayed sessions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_convoy, resume_convoy,
    validate_convoy_board, verify_convoy,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.convoy-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.convoy-package-play.v1"
MAX_PACKAGE_BYTES = 131072
MAX_PLAY_BYTES = MAX_REPORT_BYTES + MAX_PACKAGE_BYTES + 8192
PACKAGE_FIELDS = {"schema", "id", "source", "board", "package_digest"}
PLAY_FIELDS = {"schema", "package", "report", "play_digest"}


def build_convoy_package(identifier: str, source: Any, board: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_convoy_board(board, world)
    package = {
        "schema": PACKAGE_SCHEMA, "id": _identifier(identifier, "convoy package id"),
        "source": world, "board": authored,
    }
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("convoy package exceeds byte budget")
    return package


def verify_convoy_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_FIELDS, "convoy package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized convoy package")
    if package["package_digest"] != digest({
        key: value for key, value in package.items() if key != "package_digest"
    }):
        raise HarborError("convoy package digest mismatch")
    rebuilt = build_convoy_package(package["id"], package["source"], package["board"])
    if rebuilt != package:
        raise HarborError("convoy package replay mismatch")
    return {"id": rebuilt["id"], "package_digest": rebuilt["package_digest"]}


def play_convoy_package(package: Any, actions: Any, *,
                        require_complete: bool = False) -> dict[str, Any]:
    verify_convoy_package(package)
    report = build_convoy(
        package["source"], package["board"], actions, require_complete=require_complete,
    )
    play = {"schema": PLAY_SCHEMA, "package": deepcopy(package), "report": report}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("convoy package play exceeds byte budget")
    return play


def verify_convoy_package_play(play: Any, *,
                               require_complete: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_FIELDS, "convoy package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized convoy package play")
    if play["play_digest"] != digest({
        key: value for key, value in play.items() if key != "play_digest"
    }):
        raise HarborError("convoy package play digest mismatch")
    verify_convoy_package(play["package"])
    verify_convoy(play["report"], require_complete=require_complete)
    rebuilt = play_convoy_package(
        play["package"], play["report"]["actions"],
        require_complete=require_complete,
    )
    if rebuilt != play:
        raise HarborError("convoy package play replay mismatch")
    return {
        "verified": True,
        "complete": rebuilt["report"]["state"]["complete"],
        "failed": rebuilt["report"]["state"]["failed"],
        "play_digest": rebuilt["play_digest"],
        "package_digest": rebuilt["package"]["package_digest"],
    }


def resume_convoy_package(play: Any, actions: Any, *, expected_digest: str,
                          require_complete: bool = False) -> dict[str, Any]:
    verify_convoy_package_play(play)
    if type(expected_digest) is not str or expected_digest != play["play_digest"]:
        raise HarborError("stale convoy package play lease")
    advanced = resume_convoy(
        play["report"], actions, expected_digest=play["report"]["report_digest"],
        require_complete=require_complete,
    )
    rebuilt = play_convoy_package(
        play["package"], advanced["actions"], require_complete=require_complete,
    )
    if rebuilt["report"] != advanced:
        raise HarborError("convoy package continuation replay mismatch")
    return rebuilt
