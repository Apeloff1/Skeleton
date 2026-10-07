"""Era-bind facade (GB-39). Does not edit operator deck."""

from __future__ import annotations

from skeleton.simulation.era.bind import EraBind, era_bind
from skeleton.simulation.era.capabilities import capabilities
from skeleton.simulation.era.forge import GameForgeRun, forge
from skeleton.simulation.era.law import HOUSE_ERA, PACKET, VERSION

__all__ = [
    "HOUSE_ERA",
    "PACKET",
    "VERSION",
    "EraBind",
    "GameForgeRun",
    "capabilities",
    "era_bind",
    "forge",
]
