"""Executable invariants for bounded frontier components."""
from dataclasses import dataclass

@dataclass(frozen=True)
class InvariantReport:
    valid: bool
    violations: tuple[str, ...] = ()

def check_bounds(*, used: int, capacity: int, name: str = "resource") -> InvariantReport:
    violations = []
    if capacity < 0:
        violations.append(f"{name} capacity must be non-negative")
    if used < 0:
        violations.append(f"{name} usage must be non-negative")
    if used > capacity:
        violations.append(f"{name} usage exceeds capacity")
    return InvariantReport(not violations, tuple(violations))
