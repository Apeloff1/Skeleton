"""Championship end-to-end acceptance across authoring, runtime, export and replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_salvage_season import (
    append_salvage_round, start_salvage_season, verify_salvage_season,
)
from .harbor_crafting_salvage_season_package import (
    build_season_package, play_season_package, verify_season_package_play,
)
from .harbor_crafting_salvage_season_leaderboard import (
    build_season_leaderboard, verify_season_leaderboard,
)

SCHEMA = "skeleton.game.harbor.salvage-season-acceptance.v1"
MAX_BYTES = 4194304
FIELDS = {"schema", "play", "leaderboard", "acceptance_digest"}


def accept_salvage_season(source: Any, board: Any, rounds: Any) -> dict[str, Any]:
    package = build_season_package(source, board, package_id="lantern_quay_salvage_season")
    play = play_season_package(package, rounds, require_complete=True)
    status = verify_season_package_play(play, require_complete=True)
    leaderboard = build_season_leaderboard([{"player": "original_player", "save": play["save"]}])
    ranked = verify_season_leaderboard(leaderboard)
    if (not status["complete"] or ranked[0]["score"] != status["score"]
            or ranked[0]["rounds"] != status["rounds_total"]):
        raise HarborError("salvage season acceptance disagreement")
    result = {"schema": SCHEMA, "play": play, "leaderboard": leaderboard}
    result["acceptance_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("salvage season acceptance oversized")
    return result


def verify_salvage_season_acceptance(acceptance: Any) -> dict[str, Any]:
    _keys(acceptance, FIELDS, "salvage season acceptance")
    if acceptance["schema"] != SCHEMA or len(canonical(acceptance)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage season acceptance")
    if acceptance["acceptance_digest"] != digest({k: v for k, v in acceptance.items()
                                                  if k != "acceptance_digest"}):
        raise HarborError("salvage season acceptance digest mismatch")
    play = acceptance["play"]
    status = verify_season_package_play(play, require_complete=True)
    rounds = [report["actions"] for report in play["save"]["reports"]]
    rebuilt = accept_salvage_season(play["package"]["source"],
                                    play["package"]["board"], rounds)
    if rebuilt != acceptance:
        raise HarborError("salvage season acceptance replay mismatch")
    return deepcopy(status)
