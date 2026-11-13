"""Bounded keyboard/controller events translated into canonical offline-grid commands.

Input is a *single discrete press*, not a claim of a native Godot driver.
The canonical Session.step remains sole authority for collision and endings.
"""
from __future__ import annotations

from dataclasses import dataclass

from .flgb_gameplay_runtime import GameplayContractError
from .offline_grid_campaign import Command, Session

_KEYS = {"ArrowUp": "north", "ArrowDown": "south", "ArrowLeft": "west",
         "ArrowRight": "east", "KeyW": "north", "KeyS": "south",
         "KeyA": "west", "KeyD": "east"}
_BUTTONS = {"dpad_up": "north", "dpad_down": "south",
            "dpad_left": "west", "dpad_right": "east"}
_ACTIONS = {"KeyE": "collect", "KeyT": "talk", "KeyF": "finish",
            "KeyX": "strike", "KeyC": "craft", "Space": "wait"}
_MAX_TARGET = 256


@dataclass(frozen=True)
class InputEvent:
    """One normalized edge; no auto-repeat, axes or browser focus implied."""
    device: str
    control: str
    pressed: bool
    target: str = ""

    def __post_init__(self) -> None:
        if self.device not in ("keyboard", "controller"):
            raise GameplayContractError("unsupported input device")
        if not isinstance(self.control, str) or len(self.control) > 64:
            raise GameplayContractError("invalid input control")
        if type(self.pressed) is not bool:
            raise GameplayContractError("invalid input edge")
        if not isinstance(self.target, str) or len(self.target) > _MAX_TARGET:
            raise GameplayContractError("invalid interaction target")


def translate(event: InputEvent, sequence: int) -> Command | None:
    """Return a replayable command or None for a release edge.

    Unknown controls and unbound actions fail closed. The caller must assign
    a monotonically increasing sequence from its authoritative session tick.
    """
    if not isinstance(event, InputEvent):
        raise GameplayContractError("invalid input event")
    if type(sequence) is not int or not 1 <= sequence <= 4096:
        raise GameplayContractError("invalid input sequence")
    mapping = _KEYS if event.device == "keyboard" else _BUTTONS
    if event.control in mapping:
        if event.target:
            raise GameplayContractError("movement cannot specify a target")
        return Command(f"input-{sequence}", "move", mapping[event.control]) if event.pressed else None
    if event.device == "keyboard" and event.control in _ACTIONS:
        action = _ACTIONS[event.control]
        if action == "wait" and event.target:
            raise GameplayContractError("wait cannot specify target")
        if action != "wait" and not event.target:
            raise GameplayContractError("interaction requires explicit target")
        return Command(f"input-{sequence}", action, event.target) if event.pressed else None
    raise GameplayContractError("unbound input control")


def apply_input(session: Session, event: InputEvent) -> Session:
    """Advance exactly one canonical tick on press; release never mutates."""
    if not isinstance(session, Session):
        raise GameplayContractError("invalid canonical session")
    command = translate(event, session.tick + 1)
    return session if command is None else session.step(command)
