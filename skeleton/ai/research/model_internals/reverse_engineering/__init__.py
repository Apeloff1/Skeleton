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
from .attention_patterns import AttentionPatternReport, AttentionPatternSample, analyze_attention_patterns
from .attribution_stability import AttributionSnapshot, AttributionStabilityReport, analyze_attribution_stability
from .cache_eviction import CacheEvictionReport, CacheTrial, analyze_cache_eviction
from .causal_trace import CausalTraceLayerReport, CausalTraceObservation, analyze_causal_trace
from .claim_gate import ClaimGateDecision, ClaimQualityEvidence, ClaimQualityGate, evaluate_claim_quality
from .circuit_graph import CircuitEdge, CircuitEdgeObservation, CircuitGraphReport, build_circuit_graph
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
from .counterfactual_consistency import CounterfactualConsistencyReport, CounterfactualPair, analyze_counterfactual_consistency
from .decoding import DecodeSample, DecodingSignature, decoding_signatures
from .differential import DifferentialFinding, compare_bundles
from .embedding_geometry import EmbeddingGeometryReport, EmbeddingSample, analyze_embedding_geometry
from .effect_size import EffectSizeReport, ScalarMeasurement, estimate_effect_size
from .evidence_chain import EvidenceChain, EvidenceChainEntry
from .evidence_synthesis import EvidenceSignal, EvidenceSynthesisReport, synthesize_evidence
from .experiment import ExperimentCell, build_experiment_matrix
from .expert_routing import ExpertRoutingObservation, ExpertRoutingReport, analyze_expert_routing
from .feature_specialization import (
    FeatureSpecializationReport,
    FeatureUnitObservation,
    analyze_feature_specialization,
)
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .intervention_localization import InterventionLocalizationReport, LayerInterventionEffect, analyze_intervention_localization
from .kv_cache import KVCacheObservation, KVCacheReport, analyze_kv_cache
from .latency_scaling import LatencyObservation, LatencyScalingReport, analyze_latency_scaling
from .logit_trajectory import LogitLensSnapshot, LogitTrajectoryReport, analyze_logit_trajectory
from .model_correspondence import CorrespondencePair, ModelCorrespondenceReport, analyze_model_correspondence
from .multimodal_adapter import AdapterProjection, MultimodalAdapterReport, analyze_multimodal_adapters
from .multimodal_alignment import MultimodalAlignmentPair, MultimodalAlignmentReport, analyze_multimodal_alignment
from .position_sensitivity import PositionSensitivityReport, PositionTrial, analyze_position_sensitivity
from .probe_calibration import ProbeCalibrationReport, ProbeControlResult, calibrate_probes
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
from .routing_stability import RoutingStabilityReport, RoutingWindow, analyze_routing_stability
from .session import ReverseEngineeringSession, SessionReport
from .state_memory import StateMemoryReport, StateTrial, analyze_state_memory
from .tokenizer_fingerprint import TokenizationSample, TokenizerFingerprint, fingerprint_tokenizer
from .subspace_overlap import SubspaceBasis, SubspaceOverlapReport, analyze_subspace_overlap
from .tool_topology import ToolCallObservation, ToolTopologyReport, analyze_tool_topology
from .topology import TopologyReport, infer_tensor_topology

__all__ = [
    "ActivationLayerReport",
    "ActivationSample",
    "AdapterProjection",
    "ArchitectureCandidate",
    "ArchitectureFamilyReport",
    "ArchitectureSignals",
    "ArtifactManifest",
    "ArtifactProvenance",
    "AttentionGeometryReport",
    "AttentionLayerShape",
    "AttentionMode",
    "AttentionPatternReport",
    "AttentionPatternSample",
    "AuthorizationScope",
    "AttributionSnapshot",
    "AttributionStabilityReport",
    "BehavioralFingerprint",
    "CacheEvictionReport",
    "CacheTrial",
    "CausalTraceLayerReport",
    "CausalTraceObservation",
    "CircuitEdge",
    "CircuitEdgeObservation",
    "CircuitGraphReport",
    "ClaimGateDecision",
    "ClaimQualityEvidence",
    "ClaimQualityGate",
    "ContextBoundaryReport",
    "ContextTrial",
    "CorrespondencePair",
    "CounterfactualConsistencyReport",
    "CounterfactualPair",
    "DecodeSample",
    "DecodingSignature",
    "DifferentialFinding",
    "EffectSizeReport",
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
    "FeatureSpecializationReport",
    "FeatureUnitObservation",
    "InferenceClaim",
    "InterventionLocalizationReport",
    "KVCacheObservation",
    "KVCacheReport",
    "LatencyObservation",
    "LatencyScalingReport",
    "LayerInterventionEffect",
    "LayerRepresentation",
    "LogitLensSnapshot",
    "LogitTrajectoryReport",
    "ModelCorrespondenceReport",
    "MultimodalAdapterReport",
    "MultimodalAlignmentPair",
    "MultimodalAlignmentReport",
    "Observation",
    "PositionSensitivityReport",
    "PositionTrial",
    "ProbeCalibrationReport",
    "ProbeCase",
    "ProbeControlResult",
    "ProbeKind",
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
    "RoutingStabilityReport",
    "RoutingWindow",
    "SessionReport",
    "StateMemoryReport",
    "ScalarMeasurement",
    "StateTrial",
    "SubspaceBasis",
    "SubspaceOverlapReport",
    "TensorRecord",
    "TokenizationSample",
    "TokenizerFingerprint",
    "ToolCallObservation",
    "ToolTopologyReport",
    "TopologyReport",
    "analyze_activation_geometry",
    "analyze_attribution_stability",
    "analyze_attention_geometry",
    "analyze_attention_patterns",
    "analyze_cache_eviction",
    "analyze_counterfactual_consistency",
    "analyze_causal_trace",
    "analyze_embedding_geometry",
    "analyze_expert_routing",
    "analyze_feature_specialization",
    "analyze_intervention_localization",
    "analyze_kv_cache",
    "analyze_latency_scaling",
    "analyze_logit_trajectory",
    "analyze_model_correspondence",
    "analyze_multimodal_adapters",
    "analyze_multimodal_alignment",
    "analyze_position_sensitivity",
    "analyze_quantization",
    "analyze_representation_drift",
    "analyze_routing_stability",
    "analyze_subspace_overlap",
    "analyze_residual_interventions",
    "analyze_state_memory",
    "analyze_tool_topology",
    "build_artifact_manifest",
    "build_circuit_graph",
    "build_experiment_matrix",
    "calibrate_probes",
    "characterize_context",
    "classify_architecture_family",
    "compare_bundles",
    "decoding_signatures",
    "estimate_effect_size",
    "evaluate_claim_quality",
    "fingerprint_bundle",
    "fingerprint_tokenizer",
    "infer_architecture",
    "infer_tensor_topology",
    "replication_status",
    "routing_fingerprint",
    "synthesize_evidence",
]
