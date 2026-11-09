"""Probe coverage — report which subsystems report health.

The dashboard wants an "are we measuring?" panel. CoverageRegistry
listens for probe registrations from other systems and notes missing
or duplicated probe names.

- :class:`CoverageAudit` — subsystem → probe names registered
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from skeleton.kernel.errors import KernelError


@dataclass
class CoverageAudit:
    subsystem: str
    probes: List[str] = field(default_factory=list)


class CoverageRegistry:
    """Track probe-name registration per subsystem."""

    def __init__(self) -> None:
        self._audits: Dict[str, CoverageAudit] = {}

    def register(self, subsystem: str, probe_name: str) -> None:
        audit = self._audits.setdefault(subsystem, CoverageAudit(subsystem=subsystem))
        if probe_name in audit.probes:
            return
        audit.probes.append(probe_name)

    def audit(self, required_subsystems: Tuple[str, ...]) -> Tuple[str, ...]:
        missing = [s for s in required_subsystems if s not in self._audits]
        if missing:
            return tuple(missing)
        return tuple()

    def summary(self) -> Dict[str, int]:
        return {
            subsystem: len(audit.probes)
            for subsystem, audit in self._audits.items()
        }
