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

from .adversarial_probe import AdversarialProbePair, AdversarialProbeReport, analyze_adversarial_probe_robustness
from .bootstrap_ci import BootstrapConfig, BootstrapInterval, bootstrap_mean_interval
from .calibration_drift import CalibrationDriftReport, CalibrationWindow, analyze_calibration_drift
from .campaign import CampaignArtifact, CampaignManifest, build_campaign_manifest
from .circuit_centrality import CircuitCentralityReport, NodeCentrality, WeightedCircuitEdge, analyze_circuit_centrality
from .circuit_motifs import CircuitMotifReport, DirectedCircuitEdge, analyze_circuit_motifs
from .claim_registry import ClaimRecord, ClaimRegistry, ClaimTransition
from .contradiction_matrix import ContradictionMatrixReport, ContradictionPair, PropositionEvidence, build_contradiction_matrix
from .cross_seed_stability import CrossSeedStabilityReport, SeedMeasurement, analyze_cross_seed_stability
from .drift_alarm import DriftAlarmReport, DriftSignal, evaluate_drift_alarm
from .evidence_quorum import DomainEvidence, EvidenceQuorumReport, evaluate_evidence_quorum
from .feature_interaction import FeatureInteractionObservation, FeatureInteractionReport, analyze_feature_interactions
from .long_context_interference import InterferenceReport, InterferenceTrial, analyze_long_context_interference
from .mediation import MediationObservation, MediationReport, analyze_mediation
from .memory_decay import MemoryDecayReport, MemoryDecayTrial, analyze_memory_decay
from .negative_control import NegativeControlObservation, NegativeControlReport, analyze_negative_controls
from .path_patching import PathPatchObservation, PathPatchReport, analyze_path_patching
from .permutation_null import PermutationTestResult, permutation_mean_difference
from .rank_sensitivity import RankedFeatureList, RankSensitivityPoint, RankSensitivityReport, analyze_rank_sensitivity
from .report_export import ReportEnvelope, build_report_envelope, verify_report_envelope
from .sequential_evidence import SequentialEvidenceReport, SequentialObservation, analyze_sequential_evidence
from .tool_policy_boundary import ToolPolicyBoundaryReport, ToolPolicyTrial, analyze_tool_policy_boundary

from .ablation_dose_response import DoseResponseReport, DoseResponseTrial, analyze_ablation_dose_response
from .assignment_balance import AssignmentBalanceReport, BalanceAssignment, analyze_assignment_balance
from .causal_directionality import DirectionalEffect, DirectionalityReport, analyze_causal_directionality
from .causal_invariance import CausalInvarianceReport, EnvironmentEffect, analyze_causal_invariance
from .circuit_discovery import CandidateEdge, CircuitCandidate, CircuitDiscoveryReport, discover_circuit_candidates
from .drift_response_policy import DriftPolicySignal, DriftResponseDecision, decide_drift_response
from .evidence_confidence import ConfidenceComponent, EvidenceConfidenceReport, aggregate_evidence_confidence
from .evidence_ledger import EvidenceLedger, EvidenceLedgerEntry
from .experiment_coverage import CoverageObservation, ExperimentCoverageReport, analyze_experiment_coverage
from .experimental_power import PowerPlan, plan_two_group_power
from .information_gain import InformationGainReport, analyze_information_gain
from .intervention_equivalence import InterventionEffectPair, InterventionEquivalenceReport, analyze_intervention_equivalence
from .intervention_specificity import InterventionSpecificityReport, SpecificityObservation, analyze_intervention_specificity
from .intervention_transfer import InterventionTransferReport, TransferObservation, analyze_intervention_transfer
from .mediation_graph import MediationEdge, MediationGraphReport, MediationPath, analyze_mediation_graph
from .multimodal_intervention import MultimodalInterventionObservation, MultimodalInterventionReport, analyze_multimodal_intervention_consistency
from .multiple_testing import AdjustedHypothesis, HypothesisPValue, MultipleTestingReport, benjamini_hochberg
from .probe_frontier import FrontierProbe, ProbeFrontierReport, analyze_probe_frontier
from .probe_redundancy import ProbeOutcomeVector, ProbeRedundancyReport, RedundantProbePair, analyze_probe_redundancy
from .probe_scheduler import ProbeSchedule, ProbeTask, schedule_probes
from .provenance_graph import ProvenanceGraphReport, ProvenanceNode, verify_provenance_graph
from .randomized_assignment import AssignedUnit, AssignmentPlan, AssignmentUnit, build_balanced_assignment
from .signature_distance import SignatureDistanceReport, analyze_signature_distance

from .adaptive_design import AdaptiveDesignDecision, AdaptiveExperimentCandidate, select_adaptive_experiments
from .bundle_verifier import BundleItem, BundleVerificationReport, verify_bundle
from .calibration_curve import CalibrationBin, CalibrationCurveReport, CalibrationPrediction, analyze_calibration_curve
from .campaign_audit import AuditCheck, CampaignAuditReport, audit_campaign
from .claim_closure import ClaimClosureDecision, ClaimClosureEvidence, ClaimClosurePolicy, evaluate_claim_closure
from .evidence_staleness import EvidenceAge, EvidenceStalenessReport, analyze_evidence_staleness
from .falsification_registry import FalsificationReport, Falsifier, evaluate_falsifiers
from .hierarchical_calibration import GroupCalibrationMetric, GroupCalibrationPrediction, HierarchicalCalibrationReport, analyze_hierarchical_calibration
from .hierarchical_uncertainty import HierarchicalObservation, HierarchicalUncertaintyReport, analyze_hierarchical_uncertainty
from .lineage_closure import LineageClosureReport, LineageNode, analyze_lineage_closure
from .missingness import MissingnessRecord, MissingnessReport, analyze_missingness
from .nonlinear_mediation import NonlinearMediationObservation, NonlinearMediationPoint, NonlinearMediationReport, analyze_nonlinear_mediation
from .replication_decay import AgedReplication, ReplicationDecayReport, analyze_replication_decay
from .replication_meta import ReplicationMetaReport, ReplicationStudy, analyze_replication_meta
from .stopping_rule import StoppingDecision, StoppingEvidence, StoppingRule, evaluate_stopping_rule
from .transport_stress import TransportStressPoint, TransportStressReport, analyze_transport_stress
from .transportability import TransportObservation, TransportabilityReport, analyze_transportability
from .version_drift import VersionDriftReport, VersionDriftStep, VersionSignature, analyze_version_drift

from .campaign_verification import CampaignVerificationControl, CampaignVerificationReport, verify_campaign
from .claim_dependencies import ClaimDependency, ClaimDependencyReport, ClaimDependencyResult, analyze_claim_dependencies
from .closure_certificate import ClosureCertificate, issue_closure_certificate, verify_closure_certificate
from .contradiction_resolution import ContradictionEvidence, ContradictionResolution, resolve_contradictions
from .evidence_refresh import EvidenceRefreshCandidate, EvidenceRefreshPlan, plan_evidence_refresh
from .evidence_supersession import EvidenceRevision, EvidenceSupersessionReport, analyze_evidence_supersession
from .experiment_replay import ReplayExpectation, ReplayObservation, ReplayVerificationReport, verify_experiment_replay
from .power_audit import PowerAuditItem, PowerAuditReport, PowerRequirement, audit_experiment_power
from .protocol_integrity import ProtocolManifest, build_protocol_manifest, verify_protocol_manifest
from .reproducibility import ReproductionRun, ReproducibilityReport, analyze_reproducibility

from .certification_bundle import CertificationArtifact, CertificationBundle, build_certification_bundle, verify_certification_bundle
from .workflow_orchestrator import WorkflowOrchestrationReport, WorkflowStageReceipt, WorkflowStageResult, orchestrate_campaign

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
    "AdversarialProbePair",
    "AdversarialProbeReport",
    "BootstrapConfig",
    "BootstrapInterval",
    "CalibrationDriftReport",
    "CalibrationWindow",
    "CampaignArtifact",
    "CampaignManifest",
    "CircuitCentralityReport",
    "CircuitMotifReport",
    "ClaimRecord",
    "ClaimRegistry",
    "ClaimTransition",
    "ContradictionMatrixReport",
    "ContradictionPair",
    "CrossSeedStabilityReport",
    "DirectedCircuitEdge",
    "DomainEvidence",
    "DriftAlarmReport",
    "DriftSignal",
    "EvidenceQuorumReport",
    "FeatureInteractionObservation",
    "FeatureInteractionReport",
    "InterferenceReport",
    "InterferenceTrial",
    "MediationObservation",
    "MediationReport",
    "MemoryDecayReport",
    "MemoryDecayTrial",
    "NegativeControlObservation",
    "NegativeControlReport",
    "NodeCentrality",
    "PathPatchObservation",
    "PathPatchReport",
    "PermutationTestResult",
    "PropositionEvidence",
    "RankSensitivityPoint",
    "RankSensitivityReport",
    "RankedFeatureList",
    "ReportEnvelope",
    "SeedMeasurement",
    "SequentialEvidenceReport",
    "SequentialObservation",
    "ToolPolicyBoundaryReport",
    "ToolPolicyTrial",
    "WeightedCircuitEdge",
    "analyze_adversarial_probe_robustness",
    "analyze_calibration_drift",
    "analyze_circuit_centrality",
    "analyze_circuit_motifs",
    "analyze_cross_seed_stability",
    "analyze_feature_interactions",
    "analyze_long_context_interference",
    "analyze_mediation",
    "analyze_memory_decay",
    "analyze_negative_controls",
    "analyze_path_patching",
    "analyze_rank_sensitivity",
    "analyze_sequential_evidence",
    "analyze_tool_policy_boundary",
    "bootstrap_mean_interval",
    "build_campaign_manifest",
    "build_contradiction_matrix",
    "build_report_envelope",
    "evaluate_drift_alarm",
    "evaluate_evidence_quorum",
    "permutation_mean_difference",
    "verify_report_envelope",
    "AdjustedHypothesis",
    "AssignedUnit",
    "AssignmentBalanceReport",
    "AssignmentPlan",
    "AssignmentUnit",
    "BalanceAssignment",
    "CandidateEdge",
    "CausalInvarianceReport",
    "CircuitCandidate",
    "CircuitDiscoveryReport",
    "ConfidenceComponent",
    "CoverageObservation",
    "DirectionalEffect",
    "DirectionalityReport",
    "DoseResponseReport",
    "DoseResponseTrial",
    "DriftPolicySignal",
    "DriftResponseDecision",
    "EnvironmentEffect",
    "EvidenceConfidenceReport",
    "EvidenceLedger",
    "EvidenceLedgerEntry",
    "ExperimentCoverageReport",
    "FrontierProbe",
    "HypothesisPValue",
    "InformationGainReport",
    "InterventionEffectPair",
    "InterventionEquivalenceReport",
    "InterventionSpecificityReport",
    "InterventionTransferReport",
    "MediationEdge",
    "MediationGraphReport",
    "MediationPath",
    "MultimodalInterventionObservation",
    "MultimodalInterventionReport",
    "MultipleTestingReport",
    "PowerPlan",
    "ProbeFrontierReport",
    "ProbeOutcomeVector",
    "ProbeRedundancyReport",
    "ProbeSchedule",
    "ProbeTask",
    "ProvenanceGraphReport",
    "ProvenanceNode",
    "RedundantProbePair",
    "SignatureDistanceReport",
    "SpecificityObservation",
    "TransferObservation",
    "aggregate_evidence_confidence",
    "analyze_ablation_dose_response",
    "analyze_assignment_balance",
    "analyze_causal_directionality",
    "analyze_causal_invariance",
    "analyze_experiment_coverage",
    "analyze_information_gain",
    "analyze_intervention_equivalence",
    "analyze_intervention_specificity",
    "analyze_intervention_transfer",
    "analyze_mediation_graph",
    "analyze_multimodal_intervention_consistency",
    "analyze_probe_frontier",
    "analyze_probe_redundancy",
    "analyze_signature_distance",
    "benjamini_hochberg",
    "build_balanced_assignment",
    "decide_drift_response",
    "discover_circuit_candidates",
    "plan_two_group_power",
    "schedule_probes",
    "verify_provenance_graph",
    "AdaptiveDesignDecision",
    "AdaptiveExperimentCandidate",
    "AgedReplication",
    "AuditCheck",
    "BundleItem",
    "BundleVerificationReport",
    "CalibrationBin",
    "CalibrationCurveReport",
    "CalibrationPrediction",
    "CampaignAuditReport",
    "ClaimClosureDecision",
    "ClaimClosureEvidence",
    "ClaimClosurePolicy",
    "EvidenceAge",
    "EvidenceStalenessReport",
    "FalsificationReport",
    "Falsifier",
    "GroupCalibrationMetric",
    "GroupCalibrationPrediction",
    "HierarchicalCalibrationReport",
    "HierarchicalObservation",
    "HierarchicalUncertaintyReport",
    "LineageClosureReport",
    "LineageNode",
    "MissingnessRecord",
    "MissingnessReport",
    "NonlinearMediationObservation",
    "NonlinearMediationPoint",
    "NonlinearMediationReport",
    "ReplicationDecayReport",
    "ReplicationMetaReport",
    "ReplicationStudy",
    "StoppingDecision",
    "StoppingEvidence",
    "StoppingRule",
    "TransportObservation",
    "TransportStressPoint",
    "TransportStressReport",
    "TransportabilityReport",
    "VersionDriftReport",
    "VersionDriftStep",
    "VersionSignature",
    "analyze_calibration_curve",
    "analyze_evidence_staleness",
    "analyze_hierarchical_calibration",
    "analyze_hierarchical_uncertainty",
    "analyze_lineage_closure",
    "analyze_missingness",
    "analyze_nonlinear_mediation",
    "analyze_replication_decay",
    "analyze_replication_meta",
    "analyze_transport_stress",
    "analyze_transportability",
    "analyze_version_drift",
    "audit_campaign",
    "evaluate_claim_closure",
    "evaluate_falsifiers",
    "evaluate_stopping_rule",
    "select_adaptive_experiments",
    "verify_bundle",
    "CampaignVerificationControl",
    "CampaignVerificationReport",
    "ClaimDependency",
    "ClaimDependencyReport",
    "ClaimDependencyResult",
    "ClosureCertificate",
    "ContradictionEvidence",
    "ContradictionResolution",
    "EvidenceRefreshCandidate",
    "EvidenceRefreshPlan",
    "EvidenceRevision",
    "EvidenceSupersessionReport",
    "PowerAuditItem",
    "PowerAuditReport",
    "PowerRequirement",
    "ProtocolManifest",
    "ReplayExpectation",
    "ReplayObservation",
    "ReplayVerificationReport",
    "ReproductionRun",
    "ReproducibilityReport",
    "analyze_claim_dependencies",
    "analyze_evidence_supersession",
    "analyze_reproducibility",
    "audit_experiment_power",
    "build_protocol_manifest",
    "issue_closure_certificate",
    "plan_evidence_refresh",
    "resolve_contradictions",
    "verify_campaign",
    "verify_closure_certificate",
    "verify_experiment_replay",
    "verify_protocol_manifest",
    "CertificationArtifact",
    "CertificationBundle",
    "WorkflowOrchestrationReport",
    "WorkflowStageReceipt",
    "WorkflowStageResult",
    "build_certification_bundle",
    "orchestrate_campaign",
    "verify_certification_bundle",
]
