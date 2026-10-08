"""VOL-157 speech completion batch. Eighty organs. Non-active plane."""

from __future__ import annotations

from skeleton.speech.vol157.conductor import Conductor
from skeleton.speech.vol157.law import CAPABILITY_COUNT, PACKET, VERSION
from skeleton.speech.vol157.registry import capabilities, index

__all__ = [
    "CAPABILITY_COUNT",
    "PACKET",
    "VERSION",
    "Conductor",
    "capabilities",
    "index",
]
