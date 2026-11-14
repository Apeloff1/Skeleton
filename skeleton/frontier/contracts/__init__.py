"""Compatibility exports for canonical Frontier runtime contracts.

The historical contract submodules remain addressable, but protocol and
provenance class identity belongs to the current runtime namespace.
"""
from skeleton.frontier.runtime.contracts import (
    AgentContract,
    MemoryContract,
    ProvenanceRecord,
    stable_content_digest,
)

from .admission_contract import AdmissionContract
from .recovery_contract import RecoveryContract

__all__ = [
    "AdmissionContract",
    "AgentContract",
    "MemoryContract",
    "ProvenanceRecord",
    "RecoveryContract",
    "stable_content_digest",
]
