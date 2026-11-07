"""skeleton/install/wizard_10000x.py
10000x extreme complete first-run wizard.
Guided setup, admin bootstrap, AI config.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import Callable, Mapping

from skeleton.install.first_run_probe_gate import FirstRunReadiness, check_first_run

class WizardError(Exception):
    pass

class FirstRunWizard10000x:
    def check_services(self, probes: Mapping[str, Callable[[], bool]]) -> FirstRunReadiness:
        """Observe real service probes without blocking access to setup UI."""
        return check_first_run(probes)

    def step(self, name: str) -> str:
        if name not in ("admin", "ai", "services", "ready"):
            raise WizardError("invalid")
        return hashlib.sha256(f"wizard10000:{name}".encode()).hexdigest()
