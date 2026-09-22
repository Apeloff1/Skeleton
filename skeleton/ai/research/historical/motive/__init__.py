"""Motive 1.0 facade (GB-21). Thin. No artifacts/Motive copy. No spine import."""

from __future__ import annotations

from skeleton.motive.capabilities import capabilities
from skeleton.motive.cards import motive_card
from skeleton.motive.engine import MotiveEngine
from skeleton.motive.heart import heart
from skeleton.motive.law import HEART_H0, PACKET, VERSION
from skeleton.motive.ops import loop_space, map_s_s_is_s, omega_sigma_iso_id, smash, suspend
from skeleton.motive.space import sphere

__all__ = [
    "HEART_H0",
    "PACKET",
    "VERSION",
    "MotiveEngine",
    "capabilities",
    "heart",
    "loop_space",
    "map_s_s_is_s",
    "motive_card",
    "omega_sigma_iso_id",
    "smash",
    "sphere",
    "suspend",
]
