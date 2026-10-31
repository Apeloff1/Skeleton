"""Checkpoint flag. Marks safe resume points in world."""
from typing import Any, Dict
class CheckpointFlag:
    def __init__(self, room: int):
        self.room = room
        self.activated = False
    def activate(self) -> None:
        self.activated = True
