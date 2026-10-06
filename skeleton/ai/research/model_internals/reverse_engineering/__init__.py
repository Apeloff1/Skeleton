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
from .attention_patterns import AttentionPatternReport, AttentionPatternSample, analyze_attention_patterns
from .attention_geometry import (
    AttentionGeometryReport,
    AttentionLayerShape,
    AttentionMode,
    analyze_attention_geometry,
)
from .cache_eviction import CacheEvictionReport, CacheTrial, analyze_cache_eviction
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
from .evidence_synthesis import EvidenceSignal, EvidenceSynthesisReport, synthesize_evidence
from .experiment import ExperimentCell, build_experiment_matrix
from .expert_routing import ExpertRoutingObservation, ExpertRoutingReport, analyze_expert_routing
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .latency_scaling import LatencyObservation, LatencyScalingReport, analyze_latency_scaling
from .logit_trajectory import LogitLensSnapshot, LogitTrajectoryReport, analyze_logit_trajectory
from .model_correspondence import CorrespondencePair, ModelCorrespondenceReport, analyze_model_correspondence
from .multimodal_adapter import AdapterProjection, MultimodalAdapterReport, analyze_multimodal_adapters
from .position_sensitivity import PositionSensitivityReport, PositionTrial, analyze_position_sensitivity
from .kv_cache import KVCacheObservation, KVCacheReport, analyze_kv_cache
from .probes import ProbeRunner
from .provenance import ArtifactProvenance, ProvenanceGate
from .quantization import QuantizationPair, QuantizationReport, analyze_quantization
from .replication import ReplicationAttempt, ReplicationStatus, replication_status
from .representation_drift import LayerRepresentation, RepresentationTransition, analyze_representation_drift
from .residual_intervention import (
    ResidualInterventionObservation,
    ResidualInterventionReport,
    analyze_residual_interventions,
)
from .routing import RoutingFingerprint, RoutingObservation, routing_fingerprint
from .session import ReverseEngineeringSession, SessionReport
from .state_memory import StateMemoryReport, StateTrial, analyze_state_memory
from .tool_topology import ToolCallObservation, ToolTopologyReport, analyze_tool_topology
from .tokenizer_fingerprint import TokenizationSample, TokenizerFingerprint, fingerprint_tokenizer
from .topology import TopologyReport, infer_tensor_topology

__all__ = [
    "ActivationLayerReport",
    "ActivationSample",
    "ArchitectureCandidate",
    "ArchitectureFamilyReport",
    "ArchitectureSignals",
    "AdapterProjection",
    "ArtifactManifest",
    "ArtifactProvenance",
    "AttentionGeometryReport",
    "AttentionPatternReport",
    "AttentionPatternSample",
    "AttentionLayerShape",
    "AttentionMode",
    "AuthorizationScope",
    "BehavioralFingerprint",
    "CacheEvictionReport",
    "CacheTrial",
    "ContextBoundaryReport",
    "CorrespondencePair",
    "ContextTrial",
    "DecodeSample",
    "DecodingSignature",
    "DifferentialFinding",
    "EmbeddingGeometryReport",
    "EmbeddingSample",
    "EvidenceBundle",
    "EvidenceChain",
    "EvidenceChainEntry",
    "EvidenceSignal",
    "EvidenceSynthesisReport",
    "ExperimentCell",
    "ExpertRoutingObservation",
    "ExpertRoutingReport",
    "InferenceClaim",
    "LatencyObservation",
    "LatencyScalingReport",
    "LayerRepresentation",
    "LogitLensSnapshot",
    "LogitTrajectoryReport",
    "KVCacheObservation",
    "KVCacheReport",
    "ModelCorrespondenceReport",
    "MultimodalAdapterReport",
    "Observation",
    "ProbeCase",
    "ProbeKind",
    "PositionSensitivityReport",
    "PositionTrial",
    "ProbeRunner",
    "ProvenanceGate",
    "QuantizationPair",
    "QuantizationReport",
    "ReplicationAttempt",
    "ReplicationStatus",
    "RepresentationTransition",
    "ResidualInterventionObservation",
    "ResidualInterventionReport",
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
    "ToolCallObservation",
    "ToolTopologyReport",
    "TopologyReport",
    "analyze_activation_geometry",
    "analyze_attention_patterns",
    "analyze_cache_eviction",
    "analyze_attention_geometry",
    "analyze_embedding_geometry",
    "analyze_expert_routing",
    "analyze_kv_cache",
    "analyze_latency_scaling",
    "analyze_logit_trajectory",
    "analyze_model_correspondence",
    "analyze_multimodal_adapters",
    "analyze_position_sensitivity",
    "analyze_quantization",
    "analyze_representation_drift",
    "analyze_residual_interventions",
    "analyze_state_memory",
    "analyze_tool_topology",
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
    "synthesize_evidence",
]
