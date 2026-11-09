"""Viscera facade (GB-22 + GB-23). No torch. No artifacts/Viscera copy."""

from __future__ import annotations

from skeleton.viscera.capabilities import capabilities
from skeleton.viscera.cards import viscera_card
from skeleton.viscera.checkgrad import checkgrad
from skeleton.viscera.engine import VisceraEngine
from skeleton.viscera.gqa import gqa_scores
from skeleton.viscera.law import PACKET, VERSION
from skeleton.viscera.logit_lens import lens
from skeleton.viscera.muon import newton_schulz
from skeleton.viscera.qk_norm import attend, qk_norm
from skeleton.viscera.quant import quant_snr
from skeleton.viscera.remat import remat
from skeleton.viscera.specdec import verify as specdec_verify
from skeleton.viscera.steer import steer
from skeleton.viscera.tape import Tape

__all__ = [
    "PACKET",
    "VERSION",
    "Tape",
    "VisceraEngine",
    "attend",
    "capabilities",
    "checkgrad",
    "gqa_scores",
    "lens",
    "newton_schulz",
    "qk_norm",
    "quant_snr",
    "remat",
    "specdec_verify",
    "steer",
    "viscera_card",
]
