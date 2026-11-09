"""Bounded terminal convoy player with real movement, combat and portable save."""
from __future__ import annotations

from typing import Any, TextIO

from .harbor_crafting import HarborError, DIRECTIONS, canonical, validate_source
from .harbor_crafting_convoy import (
    build_convoy, convoy_status, normalize_convoy_action, validate_convoy_board,
)

HELP = (
    "move north|south|east|west, gather, craft ITEM, trade ITEM, "
    "escort, strike, guard, wait, status, help, quit"
)


def _parse(line: str) -> dict[str, str]:
    words = line.strip().lower().split()
    if len(words) == 1 and words[0] in {"gather", "escort", "strike", "guard", "wait"}:
        return {"op": words[0]}
    if len(words) == 2 and words[0] == "move" and words[1] in DIRECTIONS:
        return {"op": "move", "direction": words[1]}
    if len(words) == 2 and words[0] in {"craft", "trade"}:
        return {"op": words[0], "recipe" if words[0] == "craft" else "item": words[1]}
    raise HarborError("unsupported convoy command")


def _view(world: dict[str, Any], report: dict[str, Any]) -> str:
    status = convoy_status(report)
    tiles = [list(row) for row in world["map"]]
    x, y = report["bundle"]["state"]["npc_pos"]
    tiles[y][x] = "N"
    x, y = status["position"]
    tiles[y][x] = "C"
    x, y = report["bundle"]["state"]["pos"]
    tiles[y][x] = "P"
    enemy = status["threat"]
    threat = "none" if enemy is None else enemy["id"] + ":" + str(enemy["remaining"])
    return (
        "\n".join("".join(row) for row in tiles)
        + "\nconvoy=" + str(status["waypoint"]) + "/" + str(len(report["board"]["route"]) - 1)
        + " hull=" + str(status["hull"]) + " threat=" + threat
        + " bounty=" + str(status["bounty"]) + " tick=" + str(status["tick"])
    )


def play_convoy_live(source: Any, board: Any, *, instream: TextIO,
                     outstream: TextIO, max_commands: int = 128) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_convoy_board(board, world)
    if type(max_commands) is not int or not 1 <= max_commands <= 256:
        raise HarborError("invalid convoy terminal command budget")
    actions: list[dict[str, str]] = []
    report = build_convoy(world, authored, actions)
    outstream.write("Lantern Quay Convoy | " + HELP + "\n")
    outstream.write(_view(world, report) + "\n")
    for _ in range(max_commands):
        if report["state"]["complete"] or report["state"]["failed"]:
            return report
        outstream.write("convoy> ")
        outstream.flush()
        raw = instream.readline(257)
        if not raw:
            return report
        if len(raw) > 256 or (not raw.endswith("\n") and len(raw) == 257):
            raise HarborError("convoy command exceeds byte budget")
        command = raw.strip().lower()
        if command == "quit":
            return report
        if command == "help":
            outstream.write(HELP + "\n")
            continue
        if command == "status":
            outstream.write(_view(world, report) + "\n")
            continue
        try:
            action = normalize_convoy_action(_parse(command))
            candidate = build_convoy(world, authored, actions + [action])
        except HarborError as exc:
            outstream.write("Rejected: " + str(exc) + "\n")
            continue
        actions.append(action)
        report = candidate
        outstream.write(_view(world, report) + "\n")
    raise HarborError("convoy terminal command budget exhausted")
