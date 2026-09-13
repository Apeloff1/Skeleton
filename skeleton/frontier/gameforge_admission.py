"""Composed admission pipeline: traffic class + concurrency + degradation."""
from enum import Enum


class Admission(str, Enum):
    ACCEPT = "accept"
    SHED = "shed"
    READ_ONLY = "read_only"


def decide(*, background_allowed: bool, read_only: bool, active: int, limit: int, background: bool) -> Admission:
    if not isinstance(background_allowed, bool) or not isinstance(read_only, bool) or not isinstance(background, bool):
        raise TypeError("admission flags must be bool")
    if (not isinstance(active, int) or isinstance(active, bool)
            or not isinstance(limit, int) or isinstance(limit, bool)
            or active < 0 or limit <= 0):
        raise ValueError("invalid concurrency bounds")
    if read_only:
        return Admission.READ_ONLY
    if background and not background_allowed:
        return Admission.SHED
    if active >= limit:
        return Admission.SHED
    return Admission.ACCEPT


def accepted(decision: Admission) -> bool:
    """Return whether an admission result permits normal execution."""
    if not isinstance(decision, Admission):
        raise TypeError("decision must be an Admission")
    return decision is Admission.ACCEPT


def degraded(decision: Admission) -> bool:
    """Return whether an admission result intentionally avoids normal execution."""
    if not isinstance(decision, Admission):
        raise TypeError("decision must be an Admission")
    return decision in (Admission.SHED, Admission.READ_ONLY)
