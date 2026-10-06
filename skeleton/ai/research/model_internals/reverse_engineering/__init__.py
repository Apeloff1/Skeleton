"""Governed AI reverse-engineering research primitives.

The package is intentionally research-only. It supports authorized black-box
behavioral analysis and locally-owned artifact inspection while keeping
evidence, inference, and promotion authority separate.
"""

from .contracts import (
    AuthorizationScope,
    EvidenceBundle,
    InferenceClaim,
    Observation,
    ProbeCase,
    ProbeKind,
    ReverseEngineeringError,
)
from .differential import DifferentialFinding, compare_bundles
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .probes import ProbeRunner
from .provenance import ArtifactProvenance, ProvenanceGate
from .session import ReverseEngineeringSession, SessionReport

__all__ = [
    "ArtifactProvenance",
    "AuthorizationScope",
    "BehavioralFingerprint",
    "DifferentialFinding",
    "EvidenceBundle",
    "InferenceClaim",
    "Observation",
    "ProbeCase",
    "ProbeKind",
    "ProbeRunner",
    "ProvenanceGate",
    "ReverseEngineeringError",
    "ReverseEngineeringSession",
    "SessionReport",
    "compare_bundles",
    "fingerprint_bundle",
    "infer_architecture",
]
