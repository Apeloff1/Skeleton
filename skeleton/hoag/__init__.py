"""HOAG 1.0 facade (GB-26). 12 regions. No Organism PWA copy."""

from __future__ import annotations

from skeleton.hoag.capabilities import capabilities
from skeleton.hoag.cards import hoag_card
from skeleton.hoag.engine import HoagEngine
from skeleton.hoag.law import PACKET, REGION_N, VERSION
from skeleton.hoag.plane import Warp, bind_mouth_body, region_cards

__all__ = [
    "PACKET",
    "REGION_N",
    "VERSION",
    "HoagEngine",
    "Warp",
    "bind_mouth_body",
    "capabilities",
    "hoag_card",
    "region_cards",
]
