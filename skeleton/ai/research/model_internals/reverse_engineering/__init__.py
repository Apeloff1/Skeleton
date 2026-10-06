"""Governed AI reverse-engineering research primitives.

The package is intentionally research-only. It supports authorized black-box
behavioral analysis and locally-owned artifact inspection while keeping
evidence, inference, and promotion authority separate.
"""

from .activation_geometry import ActivationLayerReport, ActivationSample, analyze_activation_geometry
from .architecture_family import (
    ArchitectureCandidate,
    ArchitectureFamilyReport,
    ArchitectureSignals,
    classify_architecture_family,
)
from .artifact_manifest import ArtifactManifest, TensorRecord, build_artifact_manifest
from .attention_geometry import (
    AttentionGeometryReport,
    AttentionLayerShape,
    AttentionMode,
    analyze_attention_geometry,
)
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
from .embedding_geometry import EmbeddingGeometryReport, EmbeddingSample, analyze_embedding_geometry
from .evidence_chain import EvidenceChain, EvidenceChainEntry
from .experiment import ExperimentCell, build_experiment_matrix
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .kv_cache import KVCacheObservation, KVCacheReport, analyze_kv_cache
from .probes import ProbeRunner
from .provenance import ArtifactProvenance, ProvenanceGate
from .quantization import QuantizationPair, QuantizationReport, analyze_quantization
from .replication import ReplicationAttempt, ReplicationStatus, replication_status
from .routing import RoutingFingerprint, RoutingObservation, routing_fingerprint
from .session import ReverseEngineeringSession, SessionReport
from .state_memory import StateMemoryReport, StateTrial, analyze_state_memory
from .tokenizer_fingerprint import TokenizationSample, TokenizerFingerprint, fingerprint_tokenizer
from .topology import TopologyReport, infer_tensor_topology

__all__ = [
    "ActivationLayerReport",
    "ActivationSample",
    "ArchitectureCandidate",
    "ArchitectureFamilyReport",
    "ArchitectureSignals",
    "ArtifactManifest",
    "ArtifactProvenance",
    "AttentionGeometryReport",
    "AttentionLayerShape",
    "AttentionMode",
    "AuthorizationScope",
    "BehavioralFingerprint",
    "ContextBoundaryReport",
    "ContextTrial",
    "DecodeSample",
    "DecodingSignature",
    "DifferentialFinding",
    "EmbeddingGeometryReport",
    "EmbeddingSample",
    "EvidenceBundle",
    "EvidenceChain",
    "EvidenceChainEntry",
    "ExperimentCell",
    "InferenceClaim",
    "KVCacheObservation",
    "KVCacheReport",
    "Observation",
    "ProbeCase",
    "ProbeKind",
    "ProbeRunner",
    "ProvenanceGate",
    "QuantizationPair",
    "QuantizationReport",
    "ReplicationAttempt",
    "ReplicationStatus",
    "ReverseEngineeringError",
    "ReverseEngineeringSession",
    "RoutingFingerprint",
    "RoutingObservation",
    "SessionReport",
    "StateMemoryReport",
    "StateTrial",
    "TensorRecord",
    "TokenizationSample",
    "TokenizerFingerprint",
    "TopologyReport",
    "analyze_activation_geometry",
    "analyze_attention_geometry",
    "analyze_embedding_geometry",
    "analyze_kv_cache",
    "analyze_quantization",
    "analyze_state_memory",
    "build_artifact_manifest",
    "build_experiment_matrix",
    "characterize_context",
    "classify_architecture_family",
    "compare_bundles",
    "decoding_signatures",
    "fingerprint_bundle",
    "fingerprint_tokenizer",
    "infer_architecture",
    "infer_tensor_topology",
    "replication_status",
    "routing_fingerprint",
]
