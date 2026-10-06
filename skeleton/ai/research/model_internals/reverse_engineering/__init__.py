"""Governed AI reverse-engineering research primitives.

The package is intentionally research-only. It supports authorized black-box
behavioral analysis and locally-owned artifact inspection while keeping
evidence, inference, and promotion authority separate.
"""

from .context_window import ContextBoundaryReport, ContextTrial, characterize_context
from .contracts import (
    AuthorizationScope,
    EvidenceBundle,
    InferenceClaim,
    Observation,
    ProbeCase,
    ProbeKind,
    ReverseEngineeringError,
)
from .decoding import DecodeSample, DecodingSignature, decoding_signatures
from .differential import DifferentialFinding, compare_bundles
from .experiment import ExperimentCell, build_experiment_matrix
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .probes import ProbeRunner
from .provenance import ArtifactProvenance, ProvenanceGate
from .replication import ReplicationAttempt, ReplicationStatus, replication_status
from .routing import RoutingFingerprint, RoutingObservation, routing_fingerprint
from .session import ReverseEngineeringSession, SessionReport
from .state_memory import StateMemoryReport, StateTrial, analyze_state_memory

__all__ = [
    "ArtifactProvenance",
    "AuthorizationScope",
    "BehavioralFingerprint",
    "ContextBoundaryReport",
    "ContextTrial",
    "DecodeSample",
    "DecodingSignature",
    "DifferentialFinding",
    "EvidenceBundle",
    "ExperimentCell",
    "InferenceClaim",
    "Observation",
    "ProbeCase",
    "ProbeKind",
    "ProbeRunner",
    "ProvenanceGate",
    "ReplicationAttempt",
    "ReplicationStatus",
    "ReverseEngineeringError",
    "ReverseEngineeringSession",
    "RoutingFingerprint",
    "RoutingObservation",
    "SessionReport",
    "StateMemoryReport",
    "StateTrial",
    "analyze_state_memory",
    "build_experiment_matrix",
    "characterize_context",
    "compare_bundles",
    "decoding_signatures",
    "fingerprint_bundle",
    "infer_architecture",
    "replication_status",
    "routing_fingerprint",
]
