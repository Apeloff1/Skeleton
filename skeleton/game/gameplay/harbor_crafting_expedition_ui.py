"""Interactive terminal expedition: legal actions, fog map, earned saves and replay."""
from __future__ import annotations

from io import TextIOBase
from typing import Any

from .harbor_crafting import HarborError, canonical, digest, validate_source
from .harbor_crafting_dialogue import validate_dialogue_board
from .harbor_crafting_expedition import (
    build_expedition, expedition_status, verify_expedition,
)
from .harbor_crafting_survey import validate_board
from .harbor_crafting_weather import validate_weather

MAX_COMMANDS = 2048
COMMANDS = {
    "north": {"op": "move", "direction": "north"},
    "south": {"op": "move", "direction": "south"},
    "east": {"op": "move", "direction": "east"},
    "west": {"op": "move", "direction": "west"},
    "wait": {"op": "wait"},
    "gather": {"op": "gather"},
    "deliver": {"op": "deliver"},
}
HELP = "north south east west wait gather craft <recipe> trade <item> talk <node> <choice> deliver choose <signal|shelter> map status save help quit"


def parse_command(line: str) -> dict[str, str] | str:
    if type(line) is not str or len(line) > 256:
        raise HarborError("invalid terminal command")
    words = line.strip().split()
    if not words:
        raise HarborError("empty terminal command")
    if len(words) == 1:
        name = words[0].lower()
        if name in COMMANDS:
            return dict(COMMANDS[name])
        if name in ("map", "status", "save", "help", "quit"):
            return name
    if len(words) == 2:
        name, value = words
        if name in ("craft", "trade", "choose"):
            return {
                "craft": {"op": "craft", "recipe": value},
                "trade": {"op": "trade", "item": value},
                "choose": {"op": "choose", "choice": value},
            }[name]
    if len(words) == 3 and words[0] == "talk":
        return {"op": "talk", "node": words[1], "choice": words[2]}
    raise HarborError("unknown terminal command")


def render_map(report: dict[str, Any]) -> str:
    world = report["source"]
    state = report["dialogue"]["bundle"]["state"]
    visible = {tuple(cell) for cell in report["survey"]["seen_tiles"]}
    remaining = {
        tuple(site["at"]) for site in report["survey_board"]["sites"]
        if site["id"] not in {visit["id"] for visit in report["survey"]["visits"]}
    }
    rows = []
    for y, row in enumerate(world["map"]):
        chars = []
        for x, tile in enumerate(row):
            pos = (x, y)
            if pos not in visible:
                chars.append("?")
            elif list(pos) == state["pos"]:
                chars.append("@")
            elif list(pos) == state["npc_pos"]:
                chars.append("N")
            elif pos in remaining:
                chars.append("*")
            else:
                chars.append(tile)
        rows.append("".join(chars))
    return "\n".join(rows)


def _write(stream: TextIOBase, line: str) -> None:
    stream.write(line + "\n")
    stream.flush()


def play_expedition_live(source: Any, survey_board: Any, weather_board: Any,
                         dialogue_board: Any, input_stream: TextIOBase,
                         output_stream: TextIOBase, *,
                         root: Any = None, expected_digest: str | None = None) -> int:
    world = validate_source(source)
    survey = validate_board(survey_board, world)
    weather = validate_weather(weather_board, world)
    dialogue = validate_dialogue_board(dialogue_board, world)
    if root is not None:
        status = verify_expedition(root)
        if type(expected_digest) is not str or status["expedition_digest"] != expected_digest:
            raise HarborError("stale interactive expedition checkpoint")
        if (root["source"] != world or root["survey_board"] != survey
                or root["weather_board"] != weather or root["dialogue_board"] != dialogue):
            raise HarborError("interactive expedition source mismatch")
        if root["dialogue"]["bundle"]["state"]["ending"] is not None:
            raise HarborError("interactive expedition already complete")
        actions = list(root["input_actions"])
        report = root
    else:
        if expected_digest is not None:
            raise HarborError("unexpected interactive expedition lease")
        actions = []
        report = build_expedition(world, survey, weather, dialogue, actions)
    _write(output_stream, "EXPEDITION_READY " + report["expedition_digest"])
    _write(output_stream, HELP)
    for _ in range(MAX_COMMANDS):
        raw = input_stream.readline(257)
        if not raw:
            _write(output_stream, "EXPEDITION_CHECKPOINT " + canonical(report).decode("utf-8"))
            return 0
        try:
            command = parse_command(raw)
        except HarborError as exc:
            _write(output_stream, "REJECTED " + str(exc))
            continue
        if command == "help":
            _write(output_stream, HELP)
            continue
        if command == "map":
            _write(output_stream, render_map(report))
            continue
        if command == "status":
            _write(output_stream, "EXPEDITION_STATUS " + canonical(expedition_status(report)).decode("utf-8"))
            continue
        if command == "save":
            _write(output_stream, "EXPEDITION_SAVE " + canonical(report).decode("utf-8"))
            continue
        if command == "quit":
            _write(output_stream, "EXPEDITION_CHECKPOINT " + canonical(report).decode("utf-8"))
            return 0
        try:
            candidate = build_expedition(world, survey, weather, dialogue,
                                         actions + [command])
        except HarborError as exc:
            _write(output_stream, "REJECTED " + str(exc))
            continue
        actions.append(command)
        report = candidate
        _write(output_stream, "ACCEPTED " + str(report["dialogue"]["bundle"]["state"]["tick"]))
        if report["complete"]:
            _write(output_stream, "EXPEDITION_WIN " + report["dialogue"]["bundle"]["state"]["ending"])
            _write(output_stream, "EXPEDITION_SAVE " + canonical(report).decode("utf-8"))
            return 0
    _write(output_stream, "EXPEDITION_LIMIT " + canonical(report).decode("utf-8"))
    return 2


def scripted_expedition_commands() -> str:
    """A fixed original authored path, not a shortcut or fabricated victory."""
    from .harbor_crafting import demo_actions
    actions = demo_actions()
    actions = actions[:16] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ] + actions[16:]
    lines = []
    for action in actions:
        op = action["op"]
        if op == "move":
            lines.append(action["direction"])
        elif op in ("craft", "trade", "choose"):
            key = {"craft": "recipe", "trade": "item", "choose": "choice"}[op]
            lines.append(op + " " + action[key])
        elif op == "talk":
            lines.append("talk " + action["node"] + " " + action["choice"])
        else:
            lines.append(op)
    return "\n".join(lines) + "\n"
