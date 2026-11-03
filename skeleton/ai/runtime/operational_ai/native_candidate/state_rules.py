"""Finite candidate run lifecycle with fail-closed uncertain-state holds."""
from __future__ import annotations
from dataclasses import dataclass

from .strict import identity
from .errors import deny

TRANSITIONS = {
    "new": frozenset({"verified", "held"}),
    "verified": frozenset({"training", "held"}),
    "training": frozenset({"candidate", "uncertain", "held"}),
    "uncertain": frozenset({"held"}),
    "candidate": frozenset({"reviewed", "held"}),
    "reviewed": frozenset({"held"}),
    "held": frozenset(),
}


@dataclass(frozen=True, slots=True)
class RunState:
    run_id: str
    state: str
    revision: int = 0

    def __post_init__(self) -> None:
        identity(self.run_id, "run")
        if type(self.state) is not str or self.state not in TRANSITIONS:
            deny("run-state-invalid")
        if type(self.revision) is not int or self.revision < 0:
            deny("run-revision")

    def advance(self, state: str) -> "RunState":
        if state not in TRANSITIONS[self.state]:
            deny("run-transition")
        return RunState(self.run_id, state, self.revision + 1)
