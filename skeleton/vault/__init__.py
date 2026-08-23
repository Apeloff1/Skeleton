"""Secrets vault subsystem — sealing, threshold sharing, rotation."""

from .shamir import Share, ShamirSeal, SealingError

__all__ = [
    "Share",
    "ShamirSeal",
    "SealingError",
]
