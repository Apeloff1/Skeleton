"""Portable authored league packages with independent replayed game sessions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy_league import (
    MAX_LEAGUE_BYTES, MAX_SAVE_BYTES, build_league, resume_league,
    validate_league, verify_league,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.convoy-league-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.convoy-league-package-play.v1"
MAX_PACKAGE_BYTES = MAX_LEAGUE_BYTES + 65536
MAX_PLAY_BYTES = MAX_SAVE_BYTES + MAX_PACKAGE_BYTES + 8192
PACKAGE_FIELDS = {"schema", "id", "source", "league", "package_digest"}
PLAY_FIELDS = {"schema", "package", "save", "play_digest"}


def build_league_package(identifier: str, source: Any, league: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_league(league, world)
    result = {
        "schema": PACKAGE_SCHEMA, "id": _identifier(identifier, "league package id"),
        "source": deepcopy(world), "league": authored,
    }
    result["package_digest"] = digest(result)
    if len(canonical(result)) > MAX_PACKAGE_BYTES:
        raise HarborError("convoy league package exceeds byte budget")
    return result


def verify_league_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_FIELDS, "league package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized league package")
    if package["package_digest"] != digest({
        key: value for key, value in package.items() if key != "package_digest"
    }):
        raise HarborError("league package digest mismatch")
    rebuilt = build_league_package(package["id"], package["source"], package["league"])
    if rebuilt != package:
        raise HarborError("league package replay mismatch")
    return {"verified": True, "package_digest": rebuilt["package_digest"]}


def play_league_package(package: Any, sessions: Any, *,
                        require_complete: bool = False) -> dict[str, Any]:
    verify_league_package(package)
    save = build_league(
        package["source"], package["league"], sessions, require_complete=require_complete,
    )
    play = {"schema": PLAY_SCHEMA, "package": deepcopy(package), "save": save}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("league package play exceeds byte budget")
    return play


def verify_league_package_play(play: Any, *,
                               require_complete: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_FIELDS, "league package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized league package play")
    if play["play_digest"] != digest({
        key: value for key, value in play.items() if key != "play_digest"
    }):
        raise HarborError("league package play digest mismatch")
    verify_league_package(play["package"])
    verify_league(play["save"], require_complete=require_complete)
    rebuilt = play_league_package(
        play["package"], play["save"]["sessions"], require_complete=require_complete,
    )
    if rebuilt != play:
        raise HarborError("league package play replay mismatch")
    return {
        "verified": True, "complete": rebuilt["save"]["complete"],
        "score": rebuilt["save"]["score"], "play_digest": rebuilt["play_digest"],
    }


def resume_league_package(play: Any, actions: Any, *, expected_digest: str,
                          require_complete: bool = False) -> dict[str, Any]:
    verify_league_package_play(play)
    if type(expected_digest) is not str or expected_digest != play["play_digest"]:
        raise HarborError("stale league package play checkpoint")
    advanced = resume_league(
        play["save"], actions, expected_digest=play["save"]["save_digest"],
        require_complete=require_complete,
    )
    result = play_league_package(
        play["package"], advanced["sessions"], require_complete=require_complete,
    )
    if result["save"] != advanced:
        raise HarborError("league package continuation replay mismatch")
    return result
