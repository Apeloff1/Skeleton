"""Crafting and industry for the gameplay economy (#807 follow-on).

* :mod:`.blueprints` — blueprints/recipes and multi-step chain planning.
* :mod:`.jobs` — build and research jobs, tick-driven build queue.
* :mod:`.research` — material (ME) and time (TE) efficiency levels.
* :mod:`.extraction` — depleting extraction nodes as capped item faucets.
* :mod:`.engine` — :class:`IndustrySystem`: wires all of the above into the
  economy ledger, the player market and inflation telemetry.
* :mod:`.telemetry` — per-period industry flows next to market inflation.
* :mod:`.save_section` — industry state as its own ``GameSavePlane`` section.
* :mod:`.replay` — command scripts and replay fingerprints.

Loot tables and UI are owned elsewhere and deliberately absent.
"""

from skeleton.economy.gameplay.industry.blueprints import Blueprint, BlueprintBook
from skeleton.economy.gameplay.industry.engine import IndustryConfig, IndustrySystem
from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.economy.gameplay.industry.extraction import ExtractionNode, NodeSpec
from skeleton.economy.gameplay.industry.research import ResearchCurve

__all__ = [
    "Blueprint",
    "BlueprintBook",
    "ExtractionNode",
    "IndustryConfig",
    "IndustryError",
    "IndustrySystem",
    "NodeSpec",
    "ResearchCurve",
]
