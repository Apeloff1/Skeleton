"""Explicit priority ordering for bounded traffic."""
from enum import IntEnum
class Priority(IntEnum):
    BULK=10
    BACKGROUND=20
    INTERACTIVE=30

def higher(a:Priority,b:Priority)->bool: return a>b
