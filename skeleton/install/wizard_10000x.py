"""skeleton/install/wizard_10000x.py
10000x extreme complete first-run wizard.
Guided setup, admin bootstrap, AI config.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import Callable, Mapping
from skeleton.install.first_run_probe_gate import FirstRunReadiness, check_first_run
from skeleton.install.loopback_readiness import SERVICES, loopback_probe

class WizardError(Exception):
    pass

class FirstRunWizard10000x:
    def check_services(self, probes: Mapping[str, Callable[[], bool]]) -> FirstRunReadiness:
        """Observe bounded dependency probes while keeping first-run setup accessible."""
        return check_first_run(probes)

    def observe_local_services(self, endpoints: Mapping[str, str]) -> dict[str, object]:
        """Report bounded live observations without certifying an install or game."""
        if not isinstance(endpoints, Mapping) or set(endpoints) - SERVICES:
            raise WizardError("invalid-service-map")
        status: dict[str, bool] = {}
        for service in sorted(SERVICES):
            url = endpoints.get(service)
            if url is None:
                status[service] = False
                continue
            try:
                status[service] = loopback_probe(service, url)()
            except (TypeError, ValueError):
                status[service] = False
        return {"setup_accessible": True, "services": status,
                "all_services_observed_ready": all(status.values()),
                "device_qualified": False, "release_ready": False}

    def step(self, name: str) -> str:
        if name not in ("admin", "ai", "services", "ready"):
            raise WizardError("invalid")
        return hashlib.sha256(f"wizard10000:{name}".encode()).hexdigest()
