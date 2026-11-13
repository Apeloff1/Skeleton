"""Hotkey binder.
Maps actions to keys for local AI or Godot input.
"""
from __future__ import annotations
from typing import Any, Dict

DEFAULT_BINDS = {
    "move_left": "A",
    "move_right": "D",
    "interact": "E",
    "salvage": "F",
    "pause": "ESC",
    "debug": "F3",
}

class HotkeyBinder:
    def __init__(self, overrides: Dict[str, str] = None):
        self.binds = dict(DEFAULT_BINDS)
        if overrides:
            self.binds.update(overrides)
    def get(self, action: str) -> str:
        return self.binds.get(action, "")
    def all(self) -> Dict[str, str]:
        return dict(self.binds)
