"""Read-only, fail-closed first-laptop operational evidence checks.

This package is NOT a provider, activation owner, installation authority or
replay database. Canonical native inference remains owned by the existing
Jeeves agent and ExecutionSpine; evidence submitted here cannot grant rights.
"""
from .runner import evaluate_domain, list_domains
from .contracts import LaptopGateHold, StageVerdict, DomainVerdict
__all__ = ["evaluate_domain", "list_domains", "LaptopGateHold",
           "StageVerdict", "DomainVerdict"]
