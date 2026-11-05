"""Terminal-first league play: canonical convoy sessions and earned standings."""
from __future__ import annotations

from typing import Any, TextIO

from .harbor_crafting import HarborError, validate_source
from .harbor_crafting_convoy_league import build_league, validate_league, verify_league
from .harbor_crafting_convoy_ui import play_convoy_live


def play_league_live(source: Any, league: Any, *, instream: TextIO,
                     outstream: TextIO, max_commands_per_round: int = 128) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_league(league, world)
    if type(max_commands_per_round) is not int or not 1 <= max_commands_per_round <= 256:
        raise HarborError("invalid league terminal command budget")
    sessions: list[list[dict[str, str]]] = []
    save = build_league(world, authored, sessions)
    outstream.write("Lantern Quay convoy league | rounds=" + str(len(authored["rounds"])) + "\n")
    for rule in authored["rounds"]:
        outstream.write("Round " + rule["id"] + " | earn bounty="
                        + str(rule["minimum_bounty"]) + " hull="
                        + str(rule["minimum_hull"]) + "\n")
        report = play_convoy_live(
            world, rule["board"], instream=instream, outstream=outstream,
            max_commands=max_commands_per_round,
        )
        if not report["actions"]:
            return save
        sessions.append(report["actions"])
        save = build_league(world, authored, sessions)
        outstream.write("League score=" + str(save["score"]) + "\n")
        if save["failed"] or not report["state"]["complete"]:
            return save
    verify_league(save)
    return save
