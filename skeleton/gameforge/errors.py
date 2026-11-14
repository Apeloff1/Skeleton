"""skeleton/gameforge/errors.py

Typed error ladder for the GameForge conductor.

Every refusal raised by the pipeline is a ``GameForgeError`` subclass with a
``rung`` (severity, ascending) and a stable ``code``. Higher rungs are more
severe; the conductor halts on any rung and never emits partial manifests.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, Optional


class Rung(IntEnum):
    """Severity ladder. Ordering is part of the public contract."""

    INPUT = 1  # malformed caller input
    PLAN = 2  # plan is structurally invalid
    ERA = 3  # era binding missing or inconsistent
    ORDER = 4  # step executed out of order / replayed
    BUDGET = 5  # resource budget exceeded (mass clip failed)
    INTEGRITY = 6  # digest/manifest mismatch: tampering or nondeterminism
    UNSAFE = 7  # content or state judged unsafe; hard refusal


class GameForgeError(Exception):
    rung: Rung = Rung.INPUT
    code: str = "gameforge.error"

    def __init__(self, message: str, *, step: Optional[str] = None, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.step = step
        self.detail = dict(detail or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "rung": int(self.rung),
            "rung_name": self.rung.name,
            "step": self.step,
            "message": self.message,
            "detail": {k: self.detail[k] for k in sorted(self.detail)},
        }


class InputError(GameForgeError):
    rung = Rung.INPUT
    code = "gameforge.input"


class PlanError(GameForgeError):
    rung = Rung.PLAN
    code = "gameforge.plan"


class EraBindingError(GameForgeError):
    rung = Rung.ERA
    code = "gameforge.era"


class StepOrderError(GameForgeError):
    rung = Rung.ORDER
    code = "gameforge.order"


class BudgetError(GameForgeError):
    rung = Rung.BUDGET
    code = "gameforge.budget"


class IntegrityError(GameForgeError):
    rung = Rung.INTEGRITY
    code = "gameforge.integrity"


class UnsafeStateError(GameForgeError):
    rung = Rung.UNSAFE
    code = "gameforge.unsafe"


LADDER = (InputError, PlanError, EraBindingError, StepOrderError, BudgetError, IntegrityError, UnsafeStateError)


def most_severe(errors):
    """Return the highest-rung error from an iterable (None if empty)."""
    best = None
    for err in errors:
        if best is None or err.rung > best.rung:
            best = err
    return best
