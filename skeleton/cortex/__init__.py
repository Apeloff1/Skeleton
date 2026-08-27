"""Cortex — the model we are building, not implementing.

PFC (small / boilerplate) · midbrain (medium / coordinator) · left/right
hemispheres · Jeeves neocortex (hivemind + trainer). Slots are ModelPorts;
backends swap; acquire copies a tract into Jeeves' own system; surpass
answers from that system.
"""
from .port import (
    SLOTS,
    SCALES,
    CallableBackend,
    EchoBackend,
    ModelPort,
    Thought,
    fingerprint,
    tokens,
)
from .pfc import TEMPLATES, PrefrontalCortex
from .midbrain import Midbrain
from .hemispheres import LeftHemisphere, RightHemisphere
from .distill import Ability, AbilityLedger, ability_from
from .neocortex import CortexTrace, JeevesCortex, local_slots

__all__ = [
    "SLOTS",
    "SCALES",
    "CallableBackend",
    "EchoBackend",
    "ModelPort",
    "Thought",
    "fingerprint",
    "tokens",
    "TEMPLATES",
    "PrefrontalCortex",
    "Midbrain",
    "LeftHemisphere",
    "RightHemisphere",
    "Ability",
    "AbilityLedger",
    "ability_from",
    "CortexTrace",
    "JeevesCortex",
    "local_slots",
]
