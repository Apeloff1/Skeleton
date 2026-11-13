"""Canonical offline grid keyboard command adapter.

Only explicit key tokens are accepted. The adapter has no access to state or
filesystem; the existing Session.step remains the collision/quest authority.
"""
from __future__ import annotations

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Command

MOVEMENT = {"w": "north", "a": "west", "s": "south", "d": "east",
            "up": "north", "left": "west", "down": "south", "right": "east"}
ACTIONS = {"collect", "talk", "craft", "strike", "finish", "wait", "move"}


def parse_terminal_input(line: str, command_id: str) -> Command:
    """Translate a terminal key/action to a replayable canonical command.

    No implicit target selection, macro expansion, repeats or arbitrary commands.
    An invalid key cannot advance the deterministic simulation tick.
    """
    if not isinstance(line, str) or len(line) > 128 or any(
        ord(char) < 32 and char not in (" ", "\t") for char in line
    ):
        raise GameplayContractError("invalid terminal input")
    parts = line.strip().split()
    if not parts or len(parts) > 2:
        raise GameplayContractError("expected action and optional target")
    key = parts[0].lower()
    if key in MOVEMENT:
        if len(parts) != 1:
            raise GameplayContractError("movement key cannot have a target")
        return Command(command_id, "move", MOVEMENT[key])
    if key not in ACTIONS:
        raise GameplayContractError("unknown terminal action")
    target = parts[1] if len(parts) == 2 else ""
    if key == "move" and target not in ("north", "south", "east", "west"):
        raise GameplayContractError("move requires direction")
    if key == "wait" and target:
        raise GameplayContractError("wait cannot have target")
    if key in {"collect", "talk", "craft", "strike", "finish"} and not target:
        raise GameplayContractError("action requires an explicit target")
    return Command(command_id, key, target)
