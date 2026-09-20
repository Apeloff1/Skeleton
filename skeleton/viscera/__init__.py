"""Viscera 2.5 facade (GB-22). No torch. No artifacts/Viscera copy."""

from __future__ import annotations

from skeleton.viscera.capabilities import capabilities
from skeleton.viscera.cards import viscera_card
from skeleton.viscera.engine import VisceraEngine
from skeleton.viscera.law import PACKET, VERSION
from skeleton.viscera.qk_norm import attend, qk_norm
from skeleton.viscera.quant import quant_snr
from skeleton.viscera.remat import remat
from skeleton.viscera.specdec import verify as specdec_verify
from skeleton.viscera.steer import steer

__all__ = [
    "PACKET",
    "VERSION",
    "VisceraEngine",
    "attend",
    "capabilities",
    "qk_norm",
    "quant_snr",
    "remat",
    "specdec_verify",
    "steer",
    "viscera_card",
]
