"""Portable choice-bound original league endings, replayed from canonical saves."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_convoy_league_consequences import (
    MAX_CONSEQUENCE_BYTES, build_league_consequences, verify_league_consequences,
)
from .harbor_crafting_convoy_league_package import (
    MAX_PACKAGE_BYTES, build_league_package, verify_league_package,
)
from .harbor_crafting_convoy_league import verify_league

SCHEMA = "skeleton.game.harbor.convoy-league-choice-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.convoy-league-choice-play.v1"
MAX_PACKAGE = MAX_PACKAGE_BYTES + 262144
MAX_PLAY = MAX_CONSEQUENCE_BYTES + MAX_PACKAGE + 8192
PACKAGE_FIELDS = {"schema", "id", "league_package", "contract_boards", "package_digest"}
PLAY_FIELDS = {"schema", "package", "consequences", "play_digest"}


def build_choice_package(identifier: str, league_package: Any,
                         contract_boards: Any) -> dict[str, Any]:
    verify_league_package(league_package)
    if not isinstance(contract_boards, list) or len(contract_boards) != len(league_package["league"]["rounds"]):
        raise HarborError("choice package board count mismatch")
    # Validate contract targets and prerequisites against an actual canonical
    # empty convoy report for each round, never against a caller-provided hint.
    from .harbor_crafting_convoy import build_convoy
    from .harbor_crafting_convoy_contracts import validate_convoy_contracts
    for round_, board in zip(league_package["league"]["rounds"], contract_boards):
        validate_convoy_contracts(
            board, build_convoy(league_package["source"], round_["board"], []),
        )
    package = {
        "schema": SCHEMA, "id": _identifier(identifier, "choice package id"),
        "league_package": deepcopy(league_package),
        "contract_boards": deepcopy(contract_boards),
    }
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE:
        raise HarborError("choice package exceeds byte budget")
    return package


def verify_choice_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_FIELDS, "choice package")
    if package["schema"] != SCHEMA or len(canonical(package)) > MAX_PACKAGE:
        raise HarborError("unsupported or oversized choice package")
    if package["package_digest"] != digest({
        key: value for key, value in package.items() if key != "package_digest"
    }):
        raise HarborError("choice package digest mismatch")
    rebuilt = build_choice_package(
        package["id"], package["league_package"], package["contract_boards"],
    )
    if rebuilt != package:
        raise HarborError("choice package replay mismatch")
    return {"verified": True, "package_digest": rebuilt["package_digest"]}


def play_choice_package(package: Any, save: Any, choices: Any, *,
                        require_all: bool = False) -> dict[str, Any]:
    verify_choice_package(package)
    verify_league(save)
    authored = package["league_package"]
    if save["source"] != authored["source"] or save["league"] != authored["league"]:
        raise HarborError("choice package save source mismatch")
    consequences = build_league_consequences(
        save, package["contract_boards"], choices, require_all=require_all,
    )
    play = {"schema": PLAY_SCHEMA, "package": deepcopy(package), "consequences": consequences}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY:
        raise HarborError("choice package play exceeds byte budget")
    return play


def verify_choice_package_play(play: Any, *, require_all: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_FIELDS, "choice package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY:
        raise HarborError("unsupported or oversized choice package play")
    if play["play_digest"] != digest({
        key: value for key, value in play.items() if key != "play_digest"
    }):
        raise HarborError("choice package play digest mismatch")
    verify_choice_package(play["package"])
    verify_league_consequences(play["consequences"], require_all=require_all)
    rebuilt = play_choice_package(
        play["package"], play["consequences"]["save"],
        play["consequences"]["choices"], require_all=require_all,
    )
    if rebuilt != play:
        raise HarborError("choice package play replay mismatch")
    return {
        "verified": True, "complete": rebuilt["consequences"]["complete"],
        "reputation": rebuilt["consequences"]["reputation"],
        "credits": rebuilt["consequences"]["credits"],
        "play_digest": rebuilt["play_digest"],
    }
