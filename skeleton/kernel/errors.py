"""
Skeleton Kernel — Errors module (canonical home)
"""

from __future__ import annotations

from enum import Enum

from skeleton.kernel.primitives import BlueprintError, MaterialisationError, SkeletonError


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"
    CRITICAL = "critical"


class VaultError(SkeletonError):
    """Vault access or audit failure."""


class ForgeError(SkeletonError):
    """Forge compile or emit failure."""


class KernelError(SkeletonError):
    """Kernel bank or dispatch failure."""


class EventBusError(KernelError):
    """Event bus failure."""


class ProfileError(KernelError):
    """Hardware profile failure."""


__all__ = [
    "SkeletonError",
    "BlueprintError",
    "MaterialisationError",
    "Severity",
    "VaultError",
    "ForgeError",
    "KernelError",
]
