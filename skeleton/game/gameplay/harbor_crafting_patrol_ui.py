"""Interactive text-first stealth patrol: real canonical turns, no eval or shell."""
from __future__ import annotations

from typing import Any, TextIO

from .harbor_crafting import HarborError, canonical, validate_source
from .harbor_crafting_patrol import (
    build_patrol, resume_patrol, validate_patrol_board, verify_patrol,
)

COMMANDS = {"north", "south", "east", "west", "wait", "hide", "smoke",
            "deliver", "gather", "extract"}
TARGETED = {"collect": "objective", "craft": "recipe", "trade": "item"}
MAX_LINE_CHARS = 192


def parse_command(line: str) -> dict[str, str] | None:
    if not isinstance(line, str) or len(line) > MAX_LINE_CHARS:
        raise HarborError("patrol command exceeds text budget")
    words = line.strip().split()
    if not words:
        raise HarborError("empty patrol command")
    if words == ["quit"]:
        return None
    if len(words) == 1 and words[0] in COMMANDS:
        if words[0] in {"north", "south", "east", "west"}:
            return {"op": "move", "direction": words[0]}
        return {"op": words[0]}
    if len(words) == 2 and words[0] == "move" and words[1] in (
            "north", "south", "east", "west"):
        return {"op": "move", "direction": words[1]}
    if len(words) == 2 and words[0] in TARGETED:
        return {"op": words[0], TARGETED[words[0]]: words[1]}
    raise HarborError("unsupported patrol command")


def render_patrol(report: dict[str, Any]) -> str:
    world = report["source"]
    board = report["board"]
    state = report["state"]
    core = report["bundle"]["state"]
    tiles = [list(row) for row in world["map"]]
    x, y = world["dock"]
    tiles[y][x] = "D"
    for objective in board["objectives"]:
        if objective["id"] not in state["collected"]:
            x, y = objective["at"]
            tiles[y][x] = "O"
    for pos in state["guards"]:
        x, y = pos
        tiles[y][x] = "G"
    x, y = core["npc_pos"]
    tiles[y][x] = "N"
    x, y = core["pos"]
    tiles[y][x] = "@"
    board_text = "\n".join("".join(row) for row in tiles)
    return (board_text + "\n"
            + "turn=" + str(state["tick"])
            + " alert=" + str(state["alert"]) + "/" + str(board["alert_limit"])
            + " score=" + str(state["score"])
            + " collected=" + ",".join(state["collected"])
            + " delivered=" + str(core["delivered"])
            + " inventory=" + str(core["inventory"])
            + " complete=" + str(state["complete"])
            + " failed=" + str(state["failed"]))


def play_live(source: Any, board: Any, *,
              input_stream: TextIO, output_stream: TextIO,
              require_complete: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_patrol_board(board, world)
    report = build_patrol(world, authored, [])
    attempts = 0
    max_attempts = 4 * authored["max_turns"]
    output_stream.write("Lantern Quay Patrol — @ player, G guard, O objective, D dock\n")
    output_stream.write("Commands: north/south/east/west, gather, craft ID, trade ID,\n")
    output_stream.write("collect ID, hide, smoke, deliver, extract, wait, quit\n")
    while attempts < max_attempts:
        output_stream.write(render_patrol(report) + "\npatrol> ")
        output_stream.flush()
        line = input_stream.readline(MAX_LINE_CHARS + 2)
        if not line:
            break
        attempts += 1
        try:
            action = parse_command(line)
            if action is None:
                break
            report = resume_patrol(
                report, [action], expected_digest=report["report_digest"],
            )
            verify_patrol(report)
        except HarborError as exc:
            output_stream.write("rejected: " + str(exc) + "\n")
            continue
        if report["state"]["complete"] or report["state"]["failed"]:
            break
    if attempts >= max_attempts and not (report["state"]["complete"] or report["state"]["failed"]):
        raise HarborError("patrol interactive attempt budget exhausted")
    if require_complete and not report["state"]["complete"]:
        raise HarborError("patrol interactive extraction not completed")
    output_stream.write("FINAL_JSON " + canonical(report).decode("utf-8") + "\n")
    return report
