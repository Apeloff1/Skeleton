"""Portable market-aware game distribution and replayed package acceptance.

Only canonical source, authored mission board and deterministic game outcomes
are packaged. No executable payload, asset download or trust in outer hashes.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest
from .harbor_crafting_market import market_report, verify_market_report
from .harbor_crafting_package import (
    build_package, play_package, verify_package, verify_package_play,
)

SCHEMA = "skeleton.game.harbor.market-distribution.v1"
PLAY_SCHEMA = "skeleton.game.harbor.market-distribution-play.v1"
MAX_BYTES = MAX_BUNDLE_BYTES * 12


def build_market_distribution(source: Any, board: Any, *, choice: str = "signal") -> dict[str, Any]:
    """Build an original playable game package with an earned economy witness."""
    package = build_package(source, board, choice=choice)
    verify_package(package)
    market = market_report(package["demo"]["bundle"])
    totals = verify_market_report(market)
    if totals["ending"] is None or not totals["delivered"]:
        raise HarborError("market distribution lacks earned victory")
    manifest = [
        {"path": "game-package.json", "sha256": digest(package), "bytes": len(canonical(package))},
        {"path": "market-demo.json", "sha256": digest(market), "bytes": len(canonical(market))},
    ]
    result = {
        "schema": SCHEMA,
        "package": package,
        "package_digest": package["package_digest"],
        "market_demo": market,
        "market_digest": market["report_digest"],
        "manifest": manifest,
    }
    result["distribution_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("market distribution exceeds byte limit")
    return result


def verify_market_distribution(distribution: Any) -> dict[str, Any]:
    _keys(distribution, {
        "schema", "package", "package_digest", "market_demo",
        "market_digest", "manifest", "distribution_digest",
    }, "market distribution")
    if distribution["schema"] != SCHEMA or len(canonical(distribution)) > MAX_BYTES:
        raise HarborError("unsupported or oversized market distribution")
    if distribution["distribution_digest"] != digest({
        k: v for k, v in distribution.items() if k != "distribution_digest"
    }):
        raise HarborError("market distribution digest mismatch")
    package = distribution["package"]
    verify_package(package)
    if distribution["package_digest"] != package["package_digest"]:
        raise HarborError("market distribution package mismatch")
    recreated = build_market_distribution(
        package["source"], package["board"], choice=package["choice"])
    if recreated != distribution:
        raise HarborError("market distribution replay mismatch")
    return {
        "id": package["id"],
        "source_digest": package["source_digest"],
        "distribution_digest": distribution["distribution_digest"],
        "demo_ending": recreated["market_demo"]["totals"]["ending"],
        "demo_coin_end": recreated["market_demo"]["totals"]["coin_end"],
    }


def play_market_distribution(distribution: Any, actions: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Play real player actions through a verified offline distribution."""
    verify_market_distribution(distribution)
    session = play_package(distribution["package"], actions, require_all=require_all)
    verify_package_play(session, require_all=require_all)
    market = market_report(session["report"]["bundle"])
    totals = verify_market_report(market)
    result = {
        "schema": PLAY_SCHEMA,
        "distribution": deepcopy(distribution),
        "distribution_digest": distribution["distribution_digest"],
        "session": session,
        "market": market,
        "market_digest": market["report_digest"],
        "totals": totals,
    }
    result["play_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES * 2:
        raise HarborError("market distribution play exceeds byte limit")
    return result


def verify_market_distribution_play(play: Any, *, require_all: bool = False) -> dict[str, Any]:
    _keys(play, {
        "schema", "distribution", "distribution_digest", "session",
        "market", "market_digest", "totals", "play_digest",
    }, "market distribution play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_BYTES * 2:
        raise HarborError("unsupported or oversized market distribution play")
    if play["play_digest"] != digest({k: v for k, v in play.items() if k != "play_digest"}):
        raise HarborError("market distribution play digest mismatch")
    distribution = play["distribution"]
    if not isinstance(distribution, dict) or play["distribution_digest"] != distribution.get("distribution_digest"):
        raise HarborError("market distribution play source mismatch")
    session = play["session"]
    if not isinstance(session, dict):
        raise HarborError("market distribution play session invalid")
    rebuilt = play_market_distribution(distribution, session["actions"], require_all=require_all)
    if rebuilt != play:
        raise HarborError("market distribution play replay mismatch")
    return deepcopy(rebuilt["totals"])
