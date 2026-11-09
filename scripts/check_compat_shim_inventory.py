#!/usr/bin/env python3
"""Fail-closed inventory of Skeleton compatibility shims.

See ``docs/CANONICAL_MODULE_BOUNDARIES.md``: a capability has one canonical
owner. Compatibility shims may exist during migration, but they must delegate
into that owner, must not grow a second production implementation, and must
never be depended on by the canonical owner.

Every discovered shim is classified as exactly one of:

* active — delegates to the canonical owner and still has a supported surface
* deprecated — still delegates, but is marked for removal
* dead — retired; invoking it must raise rather than return a value
* unknown — discovered and unclassified (always a gate failure)

Unknown rows, missing owners, reverse dependencies, and dead shims that
silently return all fail closed. This module is stdlib-only so it can run
before project dependencies are installed.
"""

from __future__ import annotations

from importlib import import_module

import ast
import re
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

STATUSES = ("active", "deprecated", "dead", "unknown")
STATUS_SET = frozenset(STATUSES)
KINDS = ("reexport", "alias", "facade", "route", "guarded", "namespace")
KIND_SET = frozenset(KINDS)

PRODUCTION_ROOTS = ("skeleton", "backend")
SKIP_PARTS = frozenset({"tests", "testing", "test", "__pycache__", ".venv", "venv"})
COMPAT_FILENAME_RE = re.compile(r"compat", re.IGNORECASE)
SHIM_DOC_RE = re.compile(
    r"backward-compatible alias"
    r"|this shim exists"
    r"|compatibility shim"
    r"|compatibility facade"
    r"|compatibility namespace"
    r"|legacy llm compatibility"
    r"|legacy compatibility surface"
    r"|legacy academy compatibility"
    r"|guarded shim\s+[—-]",
    re.IGNORECASE,
)

# Filename matches that are domain "compat" language, not module shims.
NOT_SHIM_COMPAT_PATHS = {
    "skeleton/organism/compat.py": (
        "style/mechanic/tone compatibility matrix, not a module shim"
    ),
}


class DeadShimError(RuntimeError):
    """Raised when a retired compatibility shim is invoked."""


@dataclass(frozen=True)
class Shim:
    shim_id: str
    path: str
    status: str
    canonical_path: str
    kind: str
    symbols: tuple[str, ...]
    references: tuple[str, ...]
    removal: str
    notes: str = ""


# Explicit table. Discovery of an unlisted production shim fails closed as unknown.
SHIMS: tuple[Shim, ...] = (
    Shim(
        shim_id="kernel.workqueue",
        path="skeleton/kernel/workqueue.py",
        status="deprecated",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue", "QueueFullError", "WorkItem"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Import alias onto weighted-fair DRR WorkQueue; test-locked only.",
    ),
    Shim(
        shim_id="kernel.fair_queue",
        path="skeleton/kernel/fair_queue.py",
        status="deprecated",
        canonical_path="skeleton/kernel/work_queue.py",
        kind="reexport",
        symbols=("FairWorkQueue", "QueueError", "QueueFullError", "WorkItem"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Orphan heap queue folded into work_queue; names mapped for import compat.",
    ),
    Shim(
        shim_id="kernel.vclock",
        path="skeleton/kernel/vclock.py",
        status="deprecated",
        canonical_path="skeleton/kernel/clocks.py",
        kind="reexport",
        symbols=("ClockError", "ClockRegistry", "VectorClock", "order_events"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "skeleton/testing/test_build_plan_smoke.py",
        ),
        removal="issue:#969",
        notes="Mutable duplicate folded into clocks.VectorClock.",
    ),
    Shim(
        shim_id="jeeves.core.JeevesCore",
        path="skeleton/jeeves/core.py",
        status="active",
        canonical_path="skeleton/jeeves/core.py",
        kind="alias",
        symbols=("JeevesCore",),
        references=("tests/test_ci1_jeeves_shims.py",),
        removal="issue:#969",
        notes="CI-1 alias: JeevesCore is Jeeves. llm_core.JeevesCore stays distinct.",
    ),
    Shim(
        shim_id="backend.ai_provider_compat",
        path="backend/core/ai_provider_compat.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider.py",
        kind="facade",
        symbols=("LlmChat", "UserMessage", "ChatResponse"),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/PROVIDER_RUNTIME.md",
            "backend/tests/test_ai_provider_compat.py",
        ),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Legacy chat builder routed through ProviderRegistry; not a second runtime.",
    ),
    Shim(
        shim_id="backend.emergentintegrations.chat",
        path="backend/emergentintegrations/llm/chat.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider_compat.py",
        kind="reexport",
        symbols=("ChatResponse", "LlmChat", "UserMessage"),
        references=(
            "docs/PROVIDER_RUNTIME.md",
            "scripts/check_provider_runtime_boundary.py",
        ),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Local Emergent import path; new code must use core.ai_provider.",
    ),
    Shim(
        shim_id="backend.emergentintegrations.llm",
        path="backend/emergentintegrations/llm/__init__.py",
        status="deprecated",
        canonical_path="backend/emergentintegrations/llm/chat.py",
        kind="reexport",
        symbols=("LlmChat", "UserMessage"),
        references=("docs/PROVIDER_RUNTIME.md",),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Package re-export of the local Emergent chat facade.",
    ),
    Shim(
        shim_id="backend.emergentintegrations",
        path="backend/emergentintegrations/__init__.py",
        status="deprecated",
        canonical_path="backend/core/ai_provider_compat.py",
        kind="namespace",
        symbols=(),
        references=("docs/PROVIDER_RUNTIME.md",),
        removal="docs/PROVIDER_RUNTIME.md",
        notes="Historical package path kept importable during provider migration.",
    ),
    Shim(
        shim_id="backend.academy_legacy_compat",
        path="backend/routes/academy_legacy_compat.py",
        status="deprecated",
        canonical_path="backend/routes/academy_v3.py",
        kind="route",
        symbols=("router", "get_topic_module_compat"),
        references=("backend/tests/test_academy_legacy_compat.py",),
        removal="FastAPI deprecated=True; sunset unset",
        notes="Maps retired v2 topic/module URL onto academy_v3 bible/section data.",
    ),
    Shim(
        shim_id="backend.cag_guarded",
        path="backend/services/cag.py",
        status="deprecated",
        canonical_path="skeleton/memory/prefix_renderer.py",
        kind="guarded",
        symbols=("CAGPrefix", "PrefixRegistry", "build_prefix"),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
        notes="Re-exports skeleton.memory.prefix_renderer when importable; local fallback otherwise.",
    ),
    Shim(
        shim_id="backend.mag_guarded",
        path="backend/services/mag.py",
        status="deprecated",
        canonical_path="skeleton/memory/warmer.py",
        kind="guarded",
        symbols=("Filler", "FillerStore", "MemoryWarmer"),
        references=("docs/CANONICAL_MODULE_BOUNDARIES.md",),
        removal="issue:#969",
        notes="Re-exports skeleton.memory.warmer when importable; local fallback otherwise.",
    ),
    Shim(
        shim_id="backend.server.ai_service",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/ai_assistant_svc.py",
        kind="reexport",
        symbols=("AIAssistantService", "ai_service"),
        references=("backend/services/ai_assistant_svc.py",),
        removal="issue:#969",
        notes="Phase-9 extraction re-export: from server import ai_service.",
    ),
    Shim(
        shim_id="backend.server.quantum_compiler",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/quantum_compiler_svc.py",
        kind="reexport",
        symbols=("QuantumCompilerService", "quantum_compiler"),
        references=(
            "backend/services/quantum_compiler_svc.py",
            "backend/routes/compiler_tools.py",
        ),
        removal="issue:#969",
        notes="Phase-8 extraction re-export used by compiler_tools.",
    ),
    Shim(
        shim_id="backend.server.self_healer",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/self_healer_svc.py",
        kind="reexport",
        symbols=("SelfHealingService", "self_healer"),
        references=("backend/services/self_healer_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction re-export of self_healer singleton.",
    ),
    Shim(
        shim_id="backend.server.import_export",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/import_export_svc.py",
        kind="reexport",
        symbols=("ImportExportService", "import_export"),
        references=("backend/services/import_export_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction re-export: from server import import_export.",
    ),
    Shim(
        shim_id="backend.server.ai_hub",
        path="backend/server.py",
        status="active",
        canonical_path="backend/services/ai_hub_svc.py",
        kind="reexport",
        symbols=("AIHubService", "get_ai_hub", "ai_hub"),
        references=("backend/services/ai_hub_svc.py",),
        removal="issue:#969",
        notes="Phase-7 extraction; singleton eager-inited for back-compat.",
    ),
    Shim(
        shim_id="backend.galaxy_studio.save_vault_entry",
        path="backend/routes/galaxy_studio.py",
        status="active",
        canonical_path="backend/routes/galaxy_studio_state.py",
        kind="alias",
        symbols=("_save_vault_entry",),
        references=("backend/routes/galaxy_studio.py",),
        removal="issue:#969",
        notes="Binds galaxy_studio_state.save_vault_entry for in-file call sites.",
    ),
    Shim(
        shim_id='ai.shell',
        path='skeleton/ai/shell/__init__.py',
        status="active",
        canonical_path='skeleton/shells/ai/__init__.py',
        kind="reexport",
        symbols=('AIApprovalError', 'AIApprovalRegistry', 'AIOutcomeMemory', 'AIProviderRouter', 'AISessionPhase', 'AIShellMetrics', 'AIShellSession', 'AIAction', 'AIIntent', 'AIPlanCompiler', 'AIPlanCritic', 'AIPlanProposal', 'AIPlanner', 'AITrustSnapshot', 'AITrustSnapshotBuilder', 'CompiledAIPlan', 'CritiqueFinding', 'CritiqueReport', 'CritiqueSeverity', 'DurableMerkleAuthority', 'DurableMerkleBundleCommit', 'DurableMerkleBundleConflict', 'DurableMerkleBundleCorruption', 'DurableMerkleBundleIndex', 'DurableMerkleBundleStoreError', 'DurableMerkleChainKind', 'DurableMerkleCheckpoint', 'DurableMerkleError', 'DurableMerkleHealthError', 'DurableMerkleHealthFinding', 'DurableMerkleHealthGuard', 'DurableMerkleHealthPolicy', 'DurableMerkleHealthReport', 'DurableMerkleHealthSeverity', 'DurableMerkleLeaf', 'DurableMerkleOperatorError', 'DurableMerkleOperatorResult', 'DurableMerkleOperatorStatus', 'DurableMerkleProof', 'DurableMerkleProofStep', 'DurableMerkleSide', 'DurableMerkleVerification', 'DurableSessionMerkleAuthority', 'DurableSessionMerkleBundleStore', 'DurableSessionMerkleError', 'DurableSessionMerkleOperator', 'DurableSessionMerkleProofBundle', 'DurableSessionMerkleVerification', 'IntentConstraint', 'IntentKind', 'MERKLE_ALGORITHM', 'MERKLE_CHECKPOINT_ARTIFACT', 'ModelTrustRegistry', 'PlanningResult', 'ProviderHealthRegistry', 'SignedAITrustSnapshot', 'SignedDurableMerkleCheckpoint', 'StoredDurableMerkleBundle', 'StoredDurableMerkleBundleIndex', 'VerificationCriterion',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/__init__.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.admitted_ensemble',
        path='skeleton/ai/shell/admitted_ensemble.py',
        status="active",
        canonical_path='skeleton/shells/ai/admitted_ensemble.py',
        kind="reexport",
        symbols=('AdmittedEnsembleResult', 'AdmittedEnsembleAIPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/admitted_ensemble.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.approval',
        path='skeleton/ai/shell/approval.py',
        status="active",
        canonical_path='skeleton/shells/ai/approval.py',
        kind="reexport",
        symbols=('AIPlanApproval', 'AIApprovalError', 'AIApprovalRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/approval.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.approval_quorum',
        path='skeleton/ai/shell/approval_quorum.py',
        status="active",
        canonical_path='skeleton/shells/ai/approval_quorum.py',
        kind="reexport",
        symbols=('QuorumVoteDecision', 'QuorumApprovalState', 'QuorumApprovalPolicy', 'QuorumVote', 'QuorumApproval', 'StoredQuorumApproval', 'QuorumApprovalError', 'AIApprovalQuorumStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/approval_quorum.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.assurance',
        path='skeleton/ai/shell/assurance.py',
        status="active",
        canonical_path='skeleton/shells/ai/assurance.py',
        kind="reexport",
        symbols=('AssuranceLevel', 'AIExecutionAssurancePolicy', 'AssuranceDecision', 'AIExecutionAssuranceInspector',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/assurance.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.assurance_binding',
        path='skeleton/ai/shell/assurance_binding.py',
        status="active",
        canonical_path='skeleton/shells/ai/assurance_binding.py',
        kind="reexport",
        symbols=('AssuranceBinding',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/assurance_binding.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.attempt_recovery',
        path='skeleton/ai/shell/attempt_recovery.py',
        status="active",
        canonical_path='skeleton/shells/ai/attempt_recovery.py',
        kind="reexport",
        symbols=('AttemptRecoveryDisposition', 'AttemptRecoveryExpectation', 'AttemptRecoveryReport', 'AIExecutionAttemptRecoveryInspector',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/attempt_recovery.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.audit_anchor',
        path='skeleton/ai/shell/audit_anchor.py',
        status="active",
        canonical_path='skeleton/shells/ai/audit_anchor.py',
        kind="reexport",
        symbols=('AIAuditAnchor', 'SignedAIAuditAnchor', 'AIAuditAnchorStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/audit_anchor.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.audit_export',
        path='skeleton/ai/shell/audit_export.py',
        status="active",
        canonical_path='skeleton/shells/ai/audit_export.py',
        kind="reexport",
        symbols=('AIAuditExport', 'AIAuditExporter',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/audit_export.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.audit_witness',
        path='skeleton/ai/shell/audit_witness.py',
        status="active",
        canonical_path='skeleton/shells/ai/audit_witness.py',
        kind="reexport",
        symbols=('AIAuditWitness', 'SignedAIAuditWitness', 'AuditWitnessHead', 'AuditWitnessVerification', 'AIAuditWitnessStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/audit_witness.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.authority_health',
        path='skeleton/ai/shell/authority_health.py',
        status="active",
        canonical_path='skeleton/shells/ai/authority_health.py',
        kind="reexport",
        symbols=('AuthorityHealthState', 'AuthorityHealthResult', 'AuthorityHealthProbe', 'CallableAuthorityHealthProbe', 'VersionedStateHealthProbe', 'AuthorityHealthPolicy', 'AuthorityHealthReport', 'AIAuthorityHealthGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/authority_health.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.benchmark',
        path='skeleton/ai/shell/benchmark.py',
        status="active",
        canonical_path='skeleton/shells/ai/benchmark.py',
        kind="reexport",
        symbols=('AIBenchmarkCase', 'default_benchmark_cases',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/benchmark.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.bridge',
        path='skeleton/ai/shell/bridge.py',
        status="active",
        canonical_path='skeleton/shells/ai/bridge.py',
        kind="reexport",
        symbols=('JeevesShellModelPort',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/bridge.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.budget',
        path='skeleton/ai/shell/budget.py',
        status="active",
        canonical_path='skeleton/shells/ai/budget.py',
        kind="reexport",
        symbols=('AIBudgetLimit', 'AIBudgetUsage', 'AIBudgetExceeded', 'AIBudget',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/budget.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.calibration',
        path='skeleton/ai/shell/calibration.py',
        status="active",
        canonical_path='skeleton/shells/ai/calibration.py',
        kind="reexport",
        symbols=('CalibrationSnapshot', 'AICalibration',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/calibration.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.candidates',
        path='skeleton/ai/shell/candidates.py',
        status="active",
        canonical_path='skeleton/shells/ai/candidates.py',
        kind="reexport",
        symbols=('CandidateEvaluation', 'CandidateSelection', 'CandidateSelector',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/candidates.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.catalog',
        path='skeleton/ai/shell/catalog.py',
        status="active",
        canonical_path='skeleton/shells/ai/catalog.py',
        kind="reexport",
        symbols=('AIToolCard', 'AIToolCatalog',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/catalog.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.checkpoint',
        path='skeleton/ai/shell/checkpoint.py',
        status="active",
        canonical_path='skeleton/shells/ai/checkpoint.py',
        kind="reexport",
        symbols=('AISessionCheckpoint',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/checkpoint.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.compiler',
        path='skeleton/ai/shell/compiler.py',
        status="active",
        canonical_path='skeleton/shells/ai/compiler.py',
        kind="reexport",
        symbols=('EnvironmentResolver', 'CompiledAIPlan', 'AIPlanCompiler',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/compiler.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.consensus',
        path='skeleton/ai/shell/consensus.py',
        status="active",
        canonical_path='skeleton/shells/ai/consensus.py',
        kind="reexport",
        symbols=('proposal_shape', 'proposal_shape_digest', 'ConsensusGroup', 'ConsensusReport', 'ProposalConsensus',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/consensus.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.context_planner',
        path='skeleton/ai/shell/context_planner.py',
        status="active",
        canonical_path='skeleton/shells/ai/context_planner.py',
        kind="reexport",
        symbols=('ContextPlanningResult', 'ContextAwareAIPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/context_planner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.context_policy',
        path='skeleton/ai/shell/context_policy.py',
        status="active",
        canonical_path='skeleton/shells/ai/context_policy.py',
        kind="reexport",
        symbols=('ContextPolicy', 'ContextPolicyDecision', 'ContextPolicyEngine',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/context_policy.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.context_provenance',
        path='skeleton/ai/shell/context_provenance.py',
        status="active",
        canonical_path='skeleton/shells/ai/context_provenance.py',
        kind="reexport",
        symbols=('ContextTrust', 'ContextSensitivity', 'ContextKind', 'ContextItem', 'ContextBundle',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/context_provenance.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.critic',
        path='skeleton/ai/shell/critic.py',
        status="active",
        canonical_path='skeleton/shells/ai/critic.py',
        kind="reexport",
        symbols=('CritiqueSeverity', 'CritiqueFinding', 'CritiqueReport', 'AIPlanCritic',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/critic.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.diagnostics',
        path='skeleton/ai/shell/diagnostics.py',
        status="active",
        canonical_path='skeleton/shells/ai/diagnostics.py',
        kind="reexport",
        symbols=('AIDiagnosticSeverity', 'AIDiagnosticFinding', 'AIDiagnosticsReport', 'AIShellDiagnostics',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/diagnostics.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_idempotency',
        path='skeleton/ai/shell/distributed_idempotency.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_idempotency.py',
        kind="reexport",
        symbols=('DistributedIdempotencyConfig', 'DistributedAIIdempotencyRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_idempotency.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_journal',
        path='skeleton/ai/shell/distributed_journal.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_journal.py',
        kind="reexport",
        symbols=('GENESIS_HASH', 'DistributedJournalHead', 'DistributedJournalSequenceIndex', 'DistributedJournalIndexHealth', 'DistributedJournalConflict', 'DistributedJournalCorruption', 'DistributedAIDecisionJournal',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_journal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_policy',
        path='skeleton/ai/shell/distributed_policy.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_policy.py',
        kind="reexport",
        symbols=('DistributedPolicyConfig', 'DistributedAIPolicyStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_policy.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_review',
        path='skeleton/ai/shell/distributed_review.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_review.py',
        kind="reexport",
        symbols=('DistributedReviewRecord', 'DistributedReviewClaim', 'DistributedAIReviewQueue',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_review.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_seal',
        path='skeleton/ai/shell/distributed_seal.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_seal.py',
        kind="reexport",
        symbols=('DistributedSealConfig', 'DistributedExecutionSealRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_seal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_session',
        path='skeleton/ai/shell/distributed_session.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_session.py',
        kind="reexport",
        symbols=('DistributedSessionConfig', 'DistributedAISessionStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_session.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.distributed_state',
        path='skeleton/ai/shell/distributed_state.py',
        status="active",
        canonical_path='skeleton/shells/ai/distributed_state.py',
        kind="reexport",
        symbols=('T', 'VersionedValue', 'FencedLease', 'InMemoryFencedStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/distributed_state.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_archive',
        path='skeleton/ai/shell/durable_archive.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_archive.py',
        kind="reexport",
        symbols=('DurableArchiveEntry', 'DurableArchiveManifest', 'SignedDurableArchiveManifest', 'DurableArchiveVerification', 'DurableArchiveError', 'DurableArchiveManifestBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_archive.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_archive_repair',
        path='skeleton/ai/shell/durable_archive_repair.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_archive_repair.py',
        kind="reexport",
        symbols=('ArchiveIndexRepairAction', 'ArchiveIndexRepairState', 'ArchiveIndexRepairPolicy', 'ArchiveIndexRepairPlan', 'ArchiveIndexRepairResult', 'ArchiveIndexRepairBatchReport', 'ArchiveIndexRepairError', 'DurableArchiveIndexRepairCoordinator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_archive_repair.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_archive_store',
        path='skeleton/ai/shell/durable_archive_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_archive_store.py',
        kind="reexport",
        symbols=('GENESIS_HASH', 'DurableArchivedNodeType', 'DurableArchivedNode', 'DurableArchiveRootReplica', 'DurableArchiveRootIndex', 'DurableArchiveSequenceIndex', 'DurableArchiveSequenceIndexHealth', 'DurableArchiveRootResolution', 'DurableArchiveHead', 'StoredDurableArchive', 'DurableArchiveStoreReport', 'DurableArchiveStoreError', 'DurableArchiveIndexState', 'DurableArchiveIndexHealth', 'DurableArchiveRepository', 'ArchiveBackedHistoricalChain',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_archive_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_checkpoint',
        path='skeleton/ai/shell/durable_checkpoint.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_checkpoint.py',
        kind="reexport",
        symbols=('CheckpointableEvidenceChain', 'DurableChainCheckpoint', 'SignedDurableChainCheckpoint', 'DurableCheckpointVerification', 'DurableCheckpointError', 'DurableCheckpointLookupIndex', 'DurableCheckpointIndexState', 'DurableCheckpointIndexHealth', 'DurableChainCheckpointStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_checkpoint.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_checkpoint_repair',
        path='skeleton/ai/shell/durable_checkpoint_repair.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_checkpoint_repair.py',
        kind="reexport",
        symbols=('CheckpointIndexRepairAction', 'CheckpointIndexRepairState', 'CheckpointIndexRepairPolicy', 'CheckpointIndexRepairPlan', 'CheckpointIndexRepairResult', 'CheckpointIndexRepairBatchReport', 'CheckpointIndexRepairError', 'DurableCheckpointIndexRepairCoordinator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_checkpoint_repair.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_hot_floor',
        path='skeleton/ai/shell/durable_hot_floor.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_hot_floor.py',
        kind="reexport",
        symbols=('GENESIS_HASH', 'DurableHotFloor', 'SignedDurableHotFloor', 'HotFloorPosition', 'DurableHotFloorHistoryIndex', 'DurableHotFloorHistoryReport', 'DurableHotFloorError', 'DurableHotFloorStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_hot_floor.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_merkle',
        path='skeleton/ai/shell/durable_merkle.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_merkle.py',
        kind="reexport",
        symbols=('MERKLE_ALGORITHM', 'MERKLE_CHECKPOINT_ARTIFACT', 'LEAF_DOMAIN', 'NODE_DOMAIN', 'EMPTY_DOMAIN', 'DurableMerkleChainKind', 'DurableMerkleSide', 'MerkleCheckpointChain', 'DurableMerkleLeaf', 'DurableMerkleProofStep', 'DurableMerkleCheckpoint', 'SignedDurableMerkleCheckpoint', 'DurableMerkleProof', 'DurableMerkleVerification', 'DurableMerkleError', 'DurableMerkleAuthority',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_merkle.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_merkle_health',
        path='skeleton/ai/shell/durable_merkle_health.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_merkle_health.py',
        kind="reexport",
        symbols=('DurableMerkleHealthSeverity', 'DurableMerkleHealthPolicy', 'DurableMerkleHealthFinding', 'DurableMerkleHealthReport', 'DurableMerkleHealthError', 'DurableMerkleHealthGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_merkle_health.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_merkle_operator',
        path='skeleton/ai/shell/durable_merkle_operator.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_merkle_operator.py',
        kind="reexport",
        symbols=('DurableMerkleOperatorStatus', 'DurableMerkleOperatorResult', 'DurableMerkleOperatorError', 'DurableSessionMerkleOperator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_merkle_operator.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_merkle_session',
        path='skeleton/ai/shell/durable_merkle_session.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_merkle_session.py',
        kind="reexport",
        symbols=('DurableSessionMerkleProofBundle', 'DurableSessionMerkleVerification', 'DurableSessionMerkleError', 'DurableSessionMerkleAuthority',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_merkle_session.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_merkle_store',
        path='skeleton/ai/shell/durable_merkle_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_merkle_store.py',
        kind="reexport",
        symbols=('DurableMerkleBundleIndex', 'StoredDurableMerkleBundle', 'StoredDurableMerkleBundleIndex', 'DurableMerkleBundleCommit', 'DurableMerkleBundleStoreError', 'DurableMerkleBundleConflict', 'DurableMerkleBundleCorruption', 'DurableSessionMerkleBundleStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_merkle_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_orphan_scan',
        path='skeleton/ai/shell/durable_orphan_scan.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_orphan_scan.py',
        kind="reexport",
        symbols=('GENESIS_HASH', 'DurableOrphanNodeKind', 'DurableOrphanRecordState', 'DurableOrphanScanPolicy', 'DurableOrphanNodeRecord', 'DurableOrphanScanReport', 'DurableOrphanScanError', 'DurableOrphanScanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_orphan_scan.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_proof_window',
        path='skeleton/ai/shell/durable_proof_window.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_proof_window.py',
        kind="reexport",
        symbols=('PROOF_ARTIFACT_TYPE', 'ProofWindowChain', 'DurableHistoricalProofWindow', 'SignedDurableHistoricalProofWindow', 'DurableHistoricalProofVerification', 'DurableHistoricalProofError', 'DurableHistoricalProofAuthority', 'DurableHistoricalProofIndex', 'DurableHistoricalProofStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_proof_window.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_proof_window_operator',
        path='skeleton/ai/shell/durable_proof_window_operator.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_proof_window_operator.py',
        kind="reexport",
        symbols=('DurableProofWindowState', 'DurableProofWindowPolicy', 'DurableProofWindowTarget', 'DurableProofWindowFinding', 'DurableProofWindowReport', 'DurableProofWindowFleetReport', 'DurableProofWindowOperatorError', 'DurableProofWindowOperator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_proof_window_operator.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_recovery',
        path='skeleton/ai/shell/durable_recovery.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_recovery.py',
        kind="reexport",
        symbols=('DurableRecoveryStatus', 'RecoveryFindingSeverity', 'DurableRecoveryFinding', 'DurableSessionRecoveryReport', 'DurableRecoveryVerificationError', 'DurableSessionRecoveryVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_recovery.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_retention',
        path='skeleton/ai/shell/durable_retention.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_retention.py',
        kind="reexport",
        symbols=('DurableRetentionState', 'DurableRetentionPolicy', 'ProtectedHistoricalRoot', 'DurableRetentionPlan', 'DurableRetentionError', 'DurableRetentionPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_retention.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_sequence_backfill',
        path='skeleton/ai/shell/durable_sequence_backfill.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_sequence_backfill.py',
        kind="reexport",
        symbols=('GENESIS_HASH', 'DurableSequenceBackfillPolicy', 'DurableSequenceBackfillCursor', 'DurableSequenceBackfillState', 'DurableSequenceBackfillStep', 'DurableSequenceBackfillChainReport', 'DurableSequenceBackfillFleetReport', 'DurableSequenceBackfillError', 'DurableSequenceBackfillOperator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_sequence_backfill.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_sequence_index',
        path='skeleton/ai/shell/durable_sequence_index.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_sequence_index.py',
        kind="reexport",
        symbols=('DurableSequenceIndexState', 'DurableSequenceIndexPolicy', 'DurableSequenceIndexFinding', 'DurableSequenceIndexChainReport', 'DurableSequenceIndexFleetReport', 'DurableSequenceIndexError', 'DurableSequenceIndexOperator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_sequence_index.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_session_commit',
        path='skeleton/ai/shell/durable_session_commit.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_session_commit.py',
        kind="reexport",
        symbols=('finalization_evidence_dict', 'finalization_evidence_digest', 'DurableSessionCommitPolicy', 'DurableSessionCommit', 'SignedDurableSessionCommit', 'DurableSessionCommitHead', 'StoredDurableSessionCommit', 'DurableSessionCommitPublication', 'DurableSessionCommitConflict', 'DurableSessionCommitCorruption', 'DurableSessionCommitBuilder', 'DurableSessionCommitStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_session_commit.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_session_journal',
        path='skeleton/ai/shell/durable_session_journal.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_session_journal.py',
        kind="reexport",
        symbols=('DurableSessionJournalManifest', 'DurableSessionJournalHead', 'StoredDurableSessionJournal', 'DurableSessionJournalCommit', 'DurableSessionJournalConflict', 'DurableSessionJournalCorruption', 'DurableSessionJournalStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_session_journal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_verification_cursor',
        path='skeleton/ai/shell/durable_verification_cursor.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_verification_cursor.py',
        kind="reexport",
        symbols=('IncrementallyVerifiableChain', 'DurableVerificationMode', 'DurableVerificationStatus', 'DurableVerificationPolicy', 'DurableVerificationCursor', 'SignedDurableVerificationCursor', 'DurableVerificationCursorHead', 'StoredDurableVerificationCursor', 'DurableVerificationReport', 'DurableVerificationResult', 'DurableVerificationCursorError', 'DurableVerificationCursorStore', 'DurableIncrementalVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_verification_cursor.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_verification_health',
        path='skeleton/ai/shell/durable_verification_health.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_verification_health.py',
        kind="reexport",
        symbols=('DurableVerificationSeverity', 'DurableVerificationFleetPolicy', 'DurableVerificationFinding', 'DurableChainVerificationHealth', 'DurableVerificationFleetReport', 'DurableVerificationFleetError', 'DurableVerificationFleetGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_verification_health.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.durable_verification_operator',
        path='skeleton/ai/shell/durable_verification_operator.py',
        status="active",
        canonical_path='skeleton/shells/ai/durable_verification_operator.py',
        kind="reexport",
        symbols=('DurableVerificationOperatorState', 'DurableVerificationOperatorPolicy', 'DurableVerificationOperatorChainReport', 'DurableVerificationOperatorReport', 'DurableVerificationRefreshReport', 'DurableVerificationOperatorError', 'DurableVerificationOperator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/durable_verification_operator.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.effects',
        path='skeleton/ai/shell/effects.py',
        status="active",
        canonical_path='skeleton/shells/ai/effects.py',
        kind="reexport",
        symbols=('EffectKind', 'EffectContract', 'EffectRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/effects.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.ensemble_planner',
        path='skeleton/ai/shell/ensemble_planner.py',
        status="active",
        canonical_path='skeleton/shells/ai/ensemble_planner.py',
        kind="reexport",
        symbols=('EnsembleMember', 'EnsemblePolicy', 'EnsembleAttempt', 'EnsemblePlanningResult', 'EnsembleAIPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/ensemble_planner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.eval_dataset',
        path='skeleton/ai/shell/eval_dataset.py',
        status="active",
        canonical_path='skeleton/shells/ai/eval_dataset.py',
        kind="reexport",
        symbols=('AIEvalCase', 'AIEvalDataset',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/eval_dataset.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.eval_runner',
        path='skeleton/ai/shell/eval_runner.py',
        status="active",
        canonical_path='skeleton/shells/ai/eval_runner.py',
        kind="reexport",
        symbols=('AIEvalCaseResult', 'AIEvalRun', 'AIEvalRunner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/eval_runner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.evals',
        path='skeleton/ai/shell/evals.py',
        status="active",
        canonical_path='skeleton/shells/ai/evals.py',
        kind="reexport",
        symbols=('AIEvalScore', 'AIShellEvaluator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/evals.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.execution_attempt',
        path='skeleton/ai/shell/execution_attempt.py',
        status="active",
        canonical_path='skeleton/shells/ai/execution_attempt.py',
        kind="reexport",
        symbols=('ExecutionAttemptState', 'TERMINAL_ATTEMPT_STATES', 'ExecutionAttemptRecovery', 'AIExecutionAttempt', 'StoredExecutionAttempt', 'ExecutionAttemptSessionHead', 'ExecutionAttemptConflict', 'AIExecutionAttemptStore', 'AttemptTrackingExecutionBackend',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/execution_attempt.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.execution_backend',
        path='skeleton/ai/shell/execution_backend.py',
        status="active",
        canonical_path='skeleton/shells/ai/execution_backend.py',
        kind="reexport",
        symbols=('AIPlanExecutionBackend', 'ShellServiceExecutionBackend',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/execution_backend.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.execution_evidence',
        path='skeleton/ai/shell/execution_evidence.py',
        status="active",
        canonical_path='skeleton/shells/ai/execution_evidence.py',
        kind="reexport",
        symbols=('AIExecutionEvidence', 'SignedAIExecutionEvidence', 'AIExecutionEvidenceBuilder', 'AIExecutionEvidenceStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/execution_evidence.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.execution_fence',
        path='skeleton/ai/shell/execution_fence.py',
        status="active",
        canonical_path='skeleton/shells/ai/execution_fence.py',
        kind="reexport",
        symbols=('AIExecutionFencePolicy', 'AIExecutionFenceBinding', 'AIExecutionFence', 'AIExecutionFenceError', 'AIExecutionFenceManager',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/execution_fence.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.execution_seal',
        path='skeleton/ai/shell/execution_seal.py',
        status="active",
        canonical_path='skeleton/shells/ai/execution_seal.py',
        kind="reexport",
        symbols=('ExecutionSeal', 'ExecutionSealError', 'ExecutionSealAuthority',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/execution_seal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.finalization_state',
        path='skeleton/ai/shell/finalization_state.py',
        status="active",
        canonical_path='skeleton/shells/ai/finalization_state.py',
        kind="reexport",
        symbols=('FinalizationPhase', 'FinalizationRecovery', 'AIExecutionFinalization', 'StoredExecutionFinalization', 'ExecutionFinalizationConflict', 'AIExecutionFinalizationStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/finalization_state.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.governance',
        path='skeleton/ai/shell/governance.py',
        status="active",
        canonical_path='skeleton/shells/ai/governance.py',
        kind="reexport",
        symbols=('AIGovernanceSnapshot', 'AIShellGovernance',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/governance.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.guardrails',
        path='skeleton/ai/shell/guardrails.py',
        status="active",
        canonical_path='skeleton/shells/ai/guardrails.py',
        kind="reexport",
        symbols=('GuardrailSeverity', 'GuardrailFinding', 'GuardrailReport', 'ModelOutputGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/guardrails.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.idempotency',
        path='skeleton/ai/shell/idempotency.py',
        status="active",
        canonical_path='skeleton/shells/ai/idempotency.py',
        kind="reexport",
        symbols=('AIIdempotencyRecord', 'AIIdempotencyConflict', 'AIIdempotencyRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/idempotency.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.isolation_compiler',
        path='skeleton/ai/shell/isolation_compiler.py',
        status="active",
        canonical_path='skeleton/shells/ai/isolation_compiler.py',
        kind="reexport",
        symbols=('AIIsolationDecision', 'AIIsolationCompiler',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/isolation_compiler.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.journal',
        path='skeleton/ai/shell/journal.py',
        status="active",
        canonical_path='skeleton/shells/ai/journal.py',
        kind="reexport",
        symbols=('AIDecisionEvent', 'AIDecisionJournal',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/journal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.lifecycle',
        path='skeleton/ai/shell/lifecycle.py',
        status="active",
        canonical_path='skeleton/shells/ai/lifecycle.py',
        kind="reexport",
        symbols=('AIServicePhase', 'AIServiceTransition', 'AIServiceState',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/lifecycle.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.manifest',
        path='skeleton/ai/shell/manifest.py',
        status="active",
        canonical_path='skeleton/shells/ai/manifest.py',
        kind="reexport",
        symbols=('AI_SHELL_MANIFEST_VERSION', 'AIToolManifest', 'build_manifest',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/manifest.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp',
        path='skeleton/ai/shell/mcp.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp.py',
        kind="reexport",
        symbols=('MCP_PROTOCOL_REVISION', 'MCPToolDescriptor', 'MCPToolList', 'MCPRequestEnvelope', 'MCPResponseEnvelope', 'MCPToolSurface',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_authz',
        path='skeleton/ai/shell/mcp_authz.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_authz.py',
        kind="reexport",
        symbols=('MCPPrincipalPolicy', 'MCPAuthorizationDecision', 'MCPAuthorization',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_authz.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_discovery',
        path='skeleton/ai/shell/mcp_discovery.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_discovery.py',
        kind="reexport",
        symbols=('MCPPrincipalDiscovery',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_discovery.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_gateway',
        path='skeleton/ai/shell/mcp_gateway.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_gateway.py',
        kind="reexport",
        symbols=('MCPPreparedToolCall', 'MCPAIShellGateway',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_gateway.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_replay',
        path='skeleton/ai/shell/mcp_replay.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_replay.py',
        kind="reexport",
        symbols=('MCPRequestAdmission', 'MCPRequestReplay', 'MCPReplayGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_replay.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_tasks',
        path='skeleton/ai/shell/mcp_tasks.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_tasks.py',
        kind="reexport",
        symbols=('MCPTaskState', 'MCPTask', 'MCPTaskRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_tasks.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.mcp_transport',
        path='skeleton/ai/shell/mcp_transport.py',
        status="active",
        canonical_path='skeleton/shells/ai/mcp_transport.py',
        kind="reexport",
        symbols=('MCPTransportPolicy', 'MCPTransportDecision', 'MCPTransportValidator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/mcp_transport.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.memory',
        path='skeleton/ai/shell/memory.py',
        status="active",
        canonical_path='skeleton/shells/ai/memory.py',
        kind="reexport",
        symbols=('OutcomeMemory', 'AIOutcomeMemory',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/memory.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.metrics',
        path='skeleton/ai/shell/metrics.py',
        status="active",
        canonical_path='skeleton/shells/ai/metrics.py',
        kind="reexport",
        symbols=('AICommandMetrics', 'AIShellMetrics',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/metrics.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.model_admission',
        path='skeleton/ai/shell/model_admission.py',
        status="active",
        canonical_path='skeleton/shells/ai/model_admission.py',
        kind="reexport",
        symbols=('ModelAdmissionRequirement', 'ModelAdmissionReport', 'AIModelAdmission',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/model_admission.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.model_circuit',
        path='skeleton/ai/shell/model_circuit.py',
        status="active",
        canonical_path='skeleton/shells/ai/model_circuit.py',
        kind="reexport",
        symbols=('ModelCircuitState', 'ModelCircuitPolicy', 'ModelCircuitSnapshot', 'ModelCircuitOpen', 'ModelCircuitRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/model_circuit.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.model_port',
        path='skeleton/ai/shell/model_port.py',
        status="active",
        canonical_path='skeleton/shells/ai/model_port.py',
        kind="reexport",
        symbols=('ModelPrivacyBoundary', 'ModelCapabilities', 'AIModelPort', 'CallableAIModelPort',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/model_port.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.model_registry',
        path='skeleton/ai/shell/model_registry.py',
        status="active",
        canonical_path='skeleton/shells/ai/model_registry.py',
        kind="reexport",
        symbols=('RegisteredModel', 'ModelRegistryConflict', 'AIModelRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/model_registry.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.observation',
        path='skeleton/ai/shell/observation.py',
        status="active",
        canonical_path='skeleton/shells/ai/observation.py',
        kind="reexport",
        symbols=('AIObservation', 'ObservationBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/observation.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.observation_policy',
        path='skeleton/ai/shell/observation_policy.py',
        status="active",
        canonical_path='skeleton/shells/ai/observation_policy.py',
        kind="reexport",
        symbols=('ObservationExposure', 'ObservationPolicy', 'ObservationPolicyEngine',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/observation_policy.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.orchestrator',
        path='skeleton/ai/shell/orchestrator.py',
        status="active",
        canonical_path='skeleton/shells/ai/orchestrator.py',
        kind="reexport",
        symbols=('AIReviewBundle', 'AIExecutionBundle', 'AIShellOrchestrator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/orchestrator.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.plan_cache',
        path='skeleton/ai/shell/plan_cache.py',
        status="active",
        canonical_path='skeleton/shells/ai/plan_cache.py',
        kind="reexport",
        symbols=('CachedAIPlan', 'AIPlanCache',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/plan_cache.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.planner',
        path='skeleton/ai/shell/planner.py',
        status="active",
        canonical_path='skeleton/shells/ai/planner.py',
        kind="reexport",
        symbols=('PlanningResult', 'AIPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/planner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.policy',
        path='skeleton/ai/shell/policy.py',
        status="active",
        canonical_path='skeleton/shells/ai/policy.py',
        kind="reexport",
        symbols=('AutonomyMode', 'AIPolicyDecision', 'AIShellPolicy',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/policy.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.policy_migration',
        path='skeleton/ai/shell/policy_migration.py',
        status="active",
        canonical_path='skeleton/shells/ai/policy_migration.py',
        kind="reexport",
        symbols=('AIPolicyChangeRisk', 'AIPolicyChange', 'AIPolicyMigration', 'AIPolicyMigrationPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/policy_migration.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.policy_rollout',
        path='skeleton/ai/shell/policy_rollout.py',
        status="active",
        canonical_path='skeleton/shells/ai/policy_rollout.py',
        kind="reexport",
        symbols=('AIPolicyRolloutPhase', 'AIPolicyRollout', 'AIPolicyRolloutManager',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/policy_rollout.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.policy_store',
        path='skeleton/ai/shell/policy_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/policy_store.py',
        kind="reexport",
        symbols=('AIPolicyRevision', 'AIPolicyConflict', 'AIPolicyStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/policy_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.protocol',
        path='skeleton/ai/shell/protocol.py',
        status="active",
        canonical_path='skeleton/shells/ai/protocol.py',
        kind="reexport",
        symbols=('AI_MODEL_PROTOCOL_VERSION', 'ModelProtocolError', 'AIModelRequest', 'AIModelResponse', 'parse_model_response',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/protocol.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.provenance',
        path='skeleton/ai/shell/provenance.py',
        status="active",
        canonical_path='skeleton/shells/ai/provenance.py',
        kind="reexport",
        symbols=('AIDecisionProvenance',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/provenance.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.provider_attestation',
        path='skeleton/ai/shell/provider_attestation.py',
        status="active",
        canonical_path='skeleton/shells/ai/provider_attestation.py',
        kind="reexport",
        symbols=('ProviderAttestation', 'AttestationRequirement', 'AttestationReport', 'ProviderAttestationVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/provider_attestation.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.provider_health',
        path='skeleton/ai/shell/provider_health.py',
        status="active",
        canonical_path='skeleton/shells/ai/provider_health.py',
        kind="reexport",
        symbols=('ProviderHealth', 'ProviderHealthPolicy', 'ProviderHealthSnapshot', 'ProviderHealthRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/provider_health.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.provider_router',
        path='skeleton/ai/shell/provider_router.py',
        status="active",
        canonical_path='skeleton/shells/ai/provider_router.py',
        kind="reexport",
        symbols=('ProviderRoute', 'AIProviderRouter',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/provider_router.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.quarantine',
        path='skeleton/ai/shell/quarantine.py',
        status="active",
        canonical_path='skeleton/shells/ai/quarantine.py',
        kind="reexport",
        symbols=('QuarantineTarget', 'QuarantineRecord', 'AIQuarantine',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/quarantine.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.rate_limit',
        path='skeleton/ai/shell/rate_limit.py',
        status="active",
        canonical_path='skeleton/shells/ai/rate_limit.py',
        kind="reexport",
        symbols=('AIModelRateLimit', 'AIModelRateDecision', 'AIModelRateLimiter',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/rate_limit.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.recovery',
        path='skeleton/ai/shell/recovery.py',
        status="active",
        canonical_path='skeleton/shells/ai/recovery.py',
        kind="reexport",
        symbols=('RecoveryAction', 'AIRecoveryReport', 'AIRecoveryManager',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/recovery.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.recovery_checkpoint',
        path='skeleton/ai/shell/recovery_checkpoint.py',
        status="active",
        canonical_path='skeleton/shells/ai/recovery_checkpoint.py',
        kind="reexport",
        symbols=('AIRecoveryCheckpoint',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/recovery_checkpoint.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.recovery_requirements',
        path='skeleton/ai/shell/recovery_requirements.py',
        status="active",
        canonical_path='skeleton/shells/ai/recovery_requirements.py',
        kind="reexport",
        symbols=('DurableRecoveryRequirementManifest', 'SignedDurableRecoveryRequirementManifest', 'DurableRecoveryRequirementVerification', 'DurableRecoveryRequirementConflict', 'DurableRecoveryRequirementStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/recovery_requirements.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.recovery_store',
        path='skeleton/ai/shell/recovery_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/recovery_store.py',
        kind="reexport",
        symbols=('RecoveryCheckpointRecord', 'RecoveryCheckpointHead', 'StoredRecoveryCheckpoint', 'RecoveryCheckpointCommit', 'RecoveryCheckpointConflict', 'AIRecoveryCheckpointStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/recovery_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.red_team',
        path='skeleton/ai/shell/red_team.py',
        status="active",
        canonical_path='skeleton/shells/ai/red_team.py',
        kind="reexport",
        symbols=('AIRedTeamCase', 'AIRedTeamResult', 'default_red_team_cases', 'AIRedTeamRunner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/red_team.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.regression',
        path='skeleton/ai/shell/regression.py',
        status="active",
        canonical_path='skeleton/shells/ai/regression.py',
        kind="reexport",
        symbols=('RegressionRecord', 'RegressionComparison', 'AIRegressionHistory',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/regression.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.release_channel',
        path='skeleton/ai/shell/release_channel.py',
        status="active",
        canonical_path='skeleton/shells/ai/release_channel.py',
        kind="reexport",
        symbols=('ReleaseChannelState', 'ReleaseChannelConflict', 'AIReleaseChannelStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/release_channel.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.release_evidence',
        path='skeleton/ai/shell/release_evidence.py',
        status="active",
        canonical_path='skeleton/shells/ai/release_evidence.py',
        kind="reexport",
        symbols=('ReleaseEvidence', 'ReleaseEvidenceBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/release_evidence.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.release_gate',
        path='skeleton/ai/shell/release_gate.py',
        status="active",
        canonical_path='skeleton/shells/ai/release_gate.py',
        kind="reexport",
        symbols=('ReleaseGateDecision', 'ReleaseGateResult', 'AIReleaseGate',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/release_gate.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.release_manager',
        path='skeleton/ai/shell/release_manager.py',
        status="active",
        canonical_path='skeleton/shells/ai/release_manager.py',
        kind="reexport",
        symbols=('PreparedAIRelease', 'AIReleaseManager',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/release_manager.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.release_registry',
        path='skeleton/ai/shell/release_registry.py',
        status="active",
        canonical_path='skeleton/shells/ai/release_registry.py',
        kind="reexport",
        symbols=('RegisteredRelease', 'ReleaseRegistryConflict', 'AIReleaseRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/release_registry.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.replanner',
        path='skeleton/ai/shell/replanner.py',
        status="active",
        canonical_path='skeleton/shells/ai/replanner.py',
        kind="reexport",
        symbols=('ReplanStop', 'ReplanRound', 'ReplanReport', 'BoundedReplanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/replanner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.replay',
        path='skeleton/ai/shell/replay.py',
        status="active",
        canonical_path='skeleton/shells/ai/replay.py',
        kind="reexport",
        symbols=('AIReplayReport', 'AIDecisionReplay',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/replay.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.resilient_planner',
        path='skeleton/ai/shell/resilient_planner.py',
        status="active",
        canonical_path='skeleton/shells/ai/resilient_planner.py',
        kind="reexport",
        symbols=('PlannerAttempt', 'ResilientPlanningResult', 'ResilientAIPlanner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/resilient_planner.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.resource_profile',
        path='skeleton/ai/shell/resource_profile.py',
        status="active",
        canonical_path='skeleton/shells/ai/resource_profile.py',
        kind="reexport",
        symbols=('AIResourceProfile', 'AIResourcePolicy', 'AIResourceDecision', 'AIResourceCompiler',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/resource_profile.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.review',
        path='skeleton/ai/shell/review.py',
        status="active",
        canonical_path='skeleton/shells/ai/review.py',
        kind="reexport",
        symbols=('ReviewAction', 'AIReviewView', 'AIReviewBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/review.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.review_queue',
        path='skeleton/ai/shell/review_queue.py',
        status="active",
        canonical_path='skeleton/shells/ai/review_queue.py',
        kind="reexport",
        symbols=('ReviewState', 'ReviewQueueItem', 'ReviewQueueConflict', 'AIReviewQueue',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/review_queue.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.risk',
        path='skeleton/ai/shell/risk.py',
        status="active",
        canonical_path='skeleton/shells/ai/risk.py',
        kind="reexport",
        symbols=('RiskBand', 'RiskDimension', 'RiskAssessment', 'AIRiskAssessor',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/risk.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.robust_consensus',
        path='skeleton/ai/shell/robust_consensus.py',
        status="active",
        canonical_path='skeleton/shells/ai/robust_consensus.py',
        kind="reexport",
        symbols=('ConsensusPolicy', 'RobustConsensusGroup', 'RobustConsensusReport', 'RobustProposalConsensus',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/robust_consensus.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.router',
        path='skeleton/ai/shell/router.py',
        status="active",
        canonical_path='skeleton/shells/ai/router.py',
        kind="reexport",
        symbols=('RoutedTool', 'AIToolRouter',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/router.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.runtime_trust',
        path='skeleton/ai/shell/runtime_trust.py',
        status="active",
        canonical_path='skeleton/shells/ai/runtime_trust.py',
        kind="reexport",
        symbols=('RuntimeTrustSurface', 'RuntimeModelBinding', 'RuntimeTrustEpoch', 'DurableRuntimeTrustPinStore', 'RuntimeTrustReport', 'AIRuntimeTrustGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/runtime_trust.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.runtime_trust_store',
        path='skeleton/ai/shell/runtime_trust_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/runtime_trust_store.py',
        kind="reexport",
        symbols=('RuntimeTrustPin', 'SignedRuntimeTrustPin', 'RuntimeTrustPinVerification', 'RuntimeTrustPinConflict', 'RuntimeTrustPinStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/runtime_trust_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.safety_case',
        path='skeleton/ai/shell/safety_case.py',
        status="active",
        canonical_path='skeleton/shells/ai/safety_case.py',
        kind="reexport",
        symbols=('SafetyCaseState', 'SafetyCasePolicy', 'SafetyCase', 'AISafetyCaseBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/safety_case.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.sandbox_attestation',
        path='skeleton/ai/shell/sandbox_attestation.py',
        status="active",
        canonical_path='skeleton/shells/ai/sandbox_attestation.py',
        kind="reexport",
        symbols=('SandboxCapabilities', 'SandboxAttestationReport', 'SandboxAttestationVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/sandbox_attestation.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.sandbox_backend',
        path='skeleton/ai/shell/sandbox_backend.py',
        status="active",
        canonical_path='skeleton/shells/ai/sandbox_backend.py',
        kind="reexport",
        symbols=('SandboxPlanExecutor', 'SandboxBinding', 'VerifiedSandboxExecutionBackend',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/sandbox_backend.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.sandbox_contract',
        path='skeleton/ai/shell/sandbox_contract.py',
        status="active",
        canonical_path='skeleton/shells/ai/sandbox_contract.py',
        kind="reexport",
        symbols=('AISandboxContract', 'AISandboxContractBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/sandbox_contract.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.sandbox_lifecycle',
        path='skeleton/ai/shell/sandbox_lifecycle.py',
        status="active",
        canonical_path='skeleton/shells/ai/sandbox_lifecycle.py',
        kind="reexport",
        symbols=('ArtifactScanEvidence', 'SandboxLifecycleError', 'SandboxLifecycleEvidence', 'SandboxLifecycleReport', 'SecretProjectionEvidence', 'verify_sandbox_lifecycle',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/sandbox_lifecycle.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.schema',
        path='skeleton/ai/shell/schema.py',
        status="active",
        canonical_path='skeleton/shells/ai/schema.py',
        kind="reexport",
        symbols=('action_schema', 'model_response_schema', 'schema_digest',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/schema.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.seal_registry',
        path='skeleton/ai/shell/seal_registry.py',
        status="active",
        canonical_path='skeleton/shells/ai/seal_registry.py',
        kind="reexport",
        symbols=('SealUse', 'SealReplay', 'ExecutionSealRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/seal_registry.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.session',
        path='skeleton/ai/shell/session.py',
        status="active",
        canonical_path='skeleton/shells/ai/session.py',
        kind="reexport",
        symbols=('AISessionPhase', 'AISessionTransition', 'AIShellSession',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/session.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.session_evidence',
        path='skeleton/ai/shell/session_evidence.py',
        status="active",
        canonical_path='skeleton/shells/ai/session_evidence.py',
        kind="reexport",
        symbols=('SessionReceiptEvidence', 'SessionExecutionEvidence', 'StoredSessionEvidence', 'SessionEvidenceConflict', 'SessionEvidenceStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/session_evidence.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.session_integrity',
        path='skeleton/ai/shell/session_integrity.py',
        status="active",
        canonical_path='skeleton/shells/ai/session_integrity.py',
        kind="reexport",
        symbols=('JournalInclusionResult', 'ReceiptInclusionResult', 'SessionEvidenceIntegrityReport', 'SessionEvidenceIntegrityError', 'SessionEvidenceIntegrityVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/session_integrity.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.session_journal',
        path='skeleton/ai/shell/session_journal.py',
        status="active",
        canonical_path='skeleton/shells/ai/session_journal.py',
        kind="reexport",
        symbols=('SessionJournalEvent', 'SessionJournalEvidence',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/session_journal.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.session_store',
        path='skeleton/ai/shell/session_store.py',
        status="active",
        canonical_path='skeleton/shells/ai/session_store.py',
        kind="reexport",
        symbols=('StoredAISession', 'AISessionConflict', 'AISessionStore',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/session_store.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.signed_artifact',
        path='skeleton/ai/shell/signed_artifact.py',
        status="active",
        canonical_path='skeleton/shells/ai/signed_artifact.py',
        kind="reexport",
        symbols=('SignedArtifact', 'ArtifactSignatureError', 'ArtifactSigner',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/signed_artifact.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.snapshot',
        path='skeleton/ai/shell/snapshot.py',
        status="active",
        canonical_path='skeleton/shells/ai/snapshot.py',
        kind="reexport",
        symbols=('AIShellSnapshot', 'AIShellSnapshotter',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/snapshot.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.source_digest',
        path='skeleton/ai/shell/source_digest.py',
        status="active",
        canonical_path='skeleton/shells/ai/source_digest.py',
        kind="reexport",
        symbols=('SourceDigestPolicy', 'SourceDigestError', 'SourceDigestProvider',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/source_digest.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.specialists',
        path='skeleton/ai/shell/specialists.py',
        status="active",
        canonical_path='skeleton/shells/ai/specialists.py',
        kind="reexport",
        symbols=('PlannerSpecialist', 'SpecialistRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/specialists.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.stale_guard',
        path='skeleton/ai/shell/stale_guard.py',
        status="active",
        canonical_path='skeleton/shells/ai/stale_guard.py',
        kind="reexport",
        symbols=('StalenessKind', 'StalenessFinding', 'StalenessReport', 'PlanPin', 'AIPlanStaleGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/stale_guard.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.startup_release',
        path='skeleton/ai/shell/startup_release.py',
        status="active",
        canonical_path='skeleton/shells/ai/startup_release.py',
        kind="reexport",
        symbols=('RuntimeReleaseExpectation', 'StartupReleaseReport', 'AIStartupReleaseGuard',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/startup_release.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.store_protocol',
        path='skeleton/ai/shell/store_protocol.py',
        status="active",
        canonical_path='skeleton/shells/ai/store_protocol.py',
        kind="reexport",
        symbols=('VersionedStateBackend', 'RecordListingBackend', 'FencedLeaseBackend', 'DistributedAIBackend',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/store_protocol.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.strict_recovery',
        path='skeleton/ai/shell/strict_recovery.py',
        status="active",
        canonical_path='skeleton/shells/ai/strict_recovery.py',
        kind="reexport",
        symbols=('StrictRecoveryReport', 'StrictAIRecoveryManager',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/strict_recovery.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.tool_exchange',
        path='skeleton/ai/shell/tool_exchange.py',
        status="active",
        canonical_path='skeleton/shells/ai/tool_exchange.py',
        kind="reexport",
        symbols=('AIToolCall', 'AIToolResult',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/tool_exchange.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.tool_guard',
        path='skeleton/ai/shell/tool_guard.py',
        status="active",
        canonical_path='skeleton/shells/ai/tool_guard.py',
        kind="reexport",
        symbols=('ToolGuardStage', 'ToolGuardDecision', 'ToolGuardTripwire', 'InputGuard', 'OutputGuard', 'AIToolGuardRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/tool_guard.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.trust',
        path='skeleton/ai/shell/trust.py',
        status="active",
        canonical_path='skeleton/shells/ai/trust.py',
        kind="reexport",
        symbols=('ModelTrustProfile', 'ModelTrustRegistry',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/trust.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.trust_snapshot',
        path='skeleton/ai/shell/trust_snapshot.py',
        status="active",
        canonical_path='skeleton/shells/ai/trust_snapshot.py',
        kind="reexport",
        symbols=('AITrustSnapshot', 'SignedAITrustSnapshot', 'AITrustSnapshotBuilder',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/trust_snapshot.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.types',
        path='skeleton/ai/shell/types.py',
        status="active",
        canonical_path='skeleton/shells/ai/types.py',
        kind="reexport",
        symbols=('IntentKind', 'IntentConstraint', 'VerificationCriterion', 'AIIntent', 'AIAction', 'AIPlanProposal',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/types.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.verifier',
        path='skeleton/ai/shell/verifier.py',
        status="active",
        canonical_path='skeleton/shells/ai/verifier.py',
        kind="reexport",
        symbols=('VerificationState', 'CriterionResult', 'VerificationReport', 'PlanVerifier',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/verifier.py; ai/shell is the compatibility re-export.",
    ),
    Shim(
        shim_id='ai.shell.workspace_manifest',
        path='skeleton/ai/shell/workspace_manifest.py',
        status="active",
        canonical_path='skeleton/shells/ai/workspace_manifest.py',
        kind="reexport",
        symbols=('WorkspaceEntryKind', 'WorkspaceEntry', 'WorkspaceManifest', 'WorkspaceDrift', 'WorkspaceManifestComparator',),
        references=(
            "docs/CANONICAL_MODULE_BOUNDARIES.md",
            "docs/consolidation/BYTE_IDENTICAL_MODULES.md",
            "issue:#80",
        ),
        removal="issue:#80",
        notes="Byte-identical twin of skeleton/shells/ai/workspace_manifest.py; ai/shell is the compatibility re-export.",
    ),

)


def inventory_table(shims: Iterable[Shim] = SHIMS) -> tuple[dict[str, object], ...]:
    """Return the shim table as JSON-ready rows."""
    rows = []
    for shim in shims:
        rows.append(
            {
                "id": shim.shim_id,
                "path": shim.path,
                "status": shim.status,
                "canonical_path": shim.canonical_path,
                "kind": shim.kind,
                "symbols": list(shim.symbols),
                "references": list(shim.references),
                "removal": shim.removal,
                "notes": shim.notes,
            }
        )
    return tuple(rows)


def _posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _production_python_files(root: Path) -> Iterable[Path]:
    for name in PRODUCTION_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
                continue
            yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def discover_shim_paths(
    root: Path, cache: dict[Path, ast.AST | str] | None = None
) -> dict[str, str]:
    """Map production paths that look like shims to the discovery reason."""
    found: dict[str, str] = {}
    for path in _production_python_files(root):
        rel = _posix(path, root)
        if COMPAT_FILENAME_RE.search(path.name):
            found[rel] = "filename"
            continue
        parsed = _parse(path, cache)
        if parsed == "unreadable":
            found[rel] = "unreadable"
            continue
        if isinstance(parsed, str) and parsed.startswith("SyntaxError"):
            found[rel] = "syntax-error"
            continue
        if isinstance(parsed, ast.AST) and SHIM_DOC_RE.search(ast.get_docstring(parsed) or ""):
            found[rel] = "docstring"
    return found


def _module_names_for(rel: str) -> set[str]:
    if not rel.endswith(".py"):
        return set()
    dotted = rel[: -len(".py")].replace("/", ".")
    names = {dotted}
    if dotted.startswith("backend."):
        names.add(dotted[len("backend.") :])
    return names


def _imported_names(tree: ast.AST, file_rel: str) -> set[str]:
    names: set[str] = set()
    file_parts = list(Path(file_rel).with_suffix("").parts)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            package = file_parts[:-1]
            if node.level:
                drop = node.level - 1
                if drop:
                    package = package[: len(package) - drop]
                if node.module:
                    names.add(".".join([*package, *node.module.split(".")]))
                    names.add(node.module)
                else:
                    names.add(".".join(package))
            elif node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def _parse(path: Path, cache: dict[Path, ast.AST | str] | None = None) -> ast.AST | str:
    if cache is not None and path in cache:
        return cache[path]
    text = _read_text(path)
    if text is None:
        result: ast.AST | str = "unreadable"
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                result = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            result = f"SyntaxError: {exc}"
    if cache is not None:
        cache[path] = result
    return result


def _canonical_imports_shim(
    canonical: Path,
    shim: Shim,
    repo_root: Path,
    *,
    module_level: bool,
    cache: dict[Path, ast.AST | str] | None = None,
) -> bool:
    parsed = _parse(canonical, cache)
    if not isinstance(parsed, ast.AST):
        return False
    imported = _imported_names(parsed, _posix(canonical, repo_root))
    if module_level:
        return bool(imported & _module_names_for(shim.path))
    return any(name in imported for name in shim.symbols if name)


def _shim_imports_canonical(
    shim_path: Path,
    shim: Shim,
    repo_root: Path,
    cache: dict[Path, ast.AST | str] | None = None,
) -> bool:
    if shim.path == shim.canonical_path:
        return True
    if shim.kind == "namespace":
        return True
    parsed = _parse(shim_path, cache)
    if not isinstance(parsed, ast.AST):
        return False
    imported = _imported_names(parsed, shim.path)
    canonical_modules = _module_names_for(shim.canonical_path)
    stem = Path(shim.canonical_path).stem
    return bool(imported & canonical_modules) or stem in imported


_DEAD_PROBE_IMPORTERS = {
    "backend.core.ai_provider_compat": lambda: import_module("backend.core.ai_provider_compat"),
    "backend.emergentintegrations.__init__": lambda: import_module("backend.emergentintegrations.__init__"),
    "backend.emergentintegrations.llm.__init__": lambda: import_module("backend.emergentintegrations.llm.__init__"),
    "backend.emergentintegrations.llm.chat": lambda: import_module("backend.emergentintegrations.llm.chat"),
    "backend.routes.academy_legacy_compat": lambda: import_module("backend.routes.academy_legacy_compat"),
    "backend.routes.galaxy_studio": lambda: import_module("backend.routes.galaxy_studio"),
    "backend.server": lambda: import_module("backend.server"),
    "backend.services.cag": lambda: import_module("backend.services.cag"),
    "backend.services.mag": lambda: import_module("backend.services.mag"),
    "skeleton.jeeves.core": lambda: import_module("skeleton.jeeves.core"),
    "skeleton.kernel.fair_queue": lambda: import_module("skeleton.kernel.fair_queue"),
    "skeleton.kernel.vclock": lambda: import_module("skeleton.kernel.vclock"),
    "skeleton.kernel.workqueue": lambda: import_module("skeleton.kernel.workqueue"),
}

def default_dead_probe(shim: Shim) -> object:
    """Importing a dead shim that still loads is a silent return."""
    if not shim.path.endswith(".py"):
        return shim.path
    module_name = sorted(_module_names_for(shim.path), key=len, reverse=True)[0]
    importer = _DEAD_PROBE_IMPORTERS.get(module_name)
    if importer is None:
        return f"unapproved dead-shim module: {module_name}"
    return importer()


def collect_violations(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: tuple[Shim, ...] | None = None,
    require_roots: bool = False,
    dead_probe: Callable[[Shim], object] | None = None,
) -> list[str]:
    """Return human-readable violations. Empty means the inventory is closed."""
    shims = SHIMS if inventory is None else inventory
    violations: list[str] = []
    cache: dict[Path, ast.AST | str] = {}

    if require_roots:
        for name in PRODUCTION_ROOTS:
            if not (repo_root / name).is_dir():
                violations.append(f"missing canonical source root: {name}")

    if not isinstance(shims, (list, tuple)):
        return ["compat shim inventory must be a list of Shim records"]

    seen_ids: set[str] = set()
    covered_paths: set[str] = set()
    path_counts = Counter(shim.path for shim in shims if isinstance(shim, Shim))
    for index, shim in enumerate(shims):
        label = f"shims[{index}]"
        if not isinstance(shim, Shim):
            violations.append(f"{label} must be a Shim record")
            continue
        if not shim.shim_id or shim.shim_id in seen_ids:
            violations.append(f"{label}: shim_id must be a unique non-empty string")
        seen_ids.add(shim.shim_id)
        if shim.status not in STATUS_SET:
            violations.append(f"{shim.shim_id}: status must be one of {sorted(STATUS_SET)}")
        if shim.kind not in KIND_SET:
            violations.append(f"{shim.shim_id}: kind must be one of {sorted(KIND_SET)}")
        if shim.status == "unknown":
            violations.append(f"{shim.shim_id}: unknown status fails closed")
        if shim.status in {"active", "deprecated"} and not shim.removal:
            violations.append(f"{shim.shim_id}: {shim.status} shim must declare a removal issue/date")
        if shim.status in {"active", "deprecated"} and not shim.canonical_path:
            violations.append(f"{shim.shim_id}: {shim.status} shim must declare canonical_path")
        if not shim.references:
            violations.append(f"{shim.shim_id}: references must not be empty")

        shim_file = repo_root / shim.path
        if shim.status == "dead" and not shim_file.exists():
            covered_paths.add(shim.path)
            continue
        if not shim_file.is_file():
            violations.append(f"{shim.shim_id}: missing shim path {shim.path}")
            continue
        covered_paths.add(shim.path)

        for ref in shim.references:
            if ref.startswith("issue:") or "://" in ref:
                continue
            if not (repo_root / ref).exists():
                violations.append(f"{shim.shim_id}: missing reference {ref}")

        parsed = _parse(shim_file, cache)
        if isinstance(parsed, str):
            violations.append(f"{shim.shim_id}: cannot validate Python module: {parsed}")

        if shim.canonical_path and not (repo_root / shim.canonical_path).is_file():
            violations.append(f"{shim.shim_id}: missing canonical_path {shim.canonical_path}")
        elif (
            isinstance(parsed, ast.AST)
            and shim.canonical_path
            and shim.status in {"active", "deprecated"}
        ):
            if not _shim_imports_canonical(shim_file, shim, repo_root, cache):
                violations.append(
                    f"{shim.shim_id}: shim must delegate into canonical owner {shim.canonical_path}"
                )
            canonical_file = repo_root / shim.canonical_path
            dedicated = shim.kind != "alias" and path_counts[shim.path] == 1
            if shim.path != shim.canonical_path and _canonical_imports_shim(
                canonical_file,
                shim,
                repo_root,
                module_level=dedicated,
                cache=cache,
            ):
                violations.append(
                    f"{shim.shim_id}: canonical owner must not depend back on shim"
                )

        if shim.status == "dead":
            probe = default_dead_probe if dead_probe is None else dead_probe
            try:
                result = probe(shim)
            except Exception:
                pass
            else:
                violations.append(
                    f"{shim.shim_id}: dead shim silently returned {result!r}"
                )

    discovered = discover_shim_paths(repo_root, cache)
    for rel, reason in sorted(discovered.items()):
        if rel in NOT_SHIM_COMPAT_PATHS:
            if rel in covered_paths:
                violations.append(f"{rel}: listed as both a shim and a non-shim compat path")
            continue
        if rel not in covered_paths:
            violations.append(f"{rel}: unknown compatibility shim ({reason})")

    return violations


def render_table(shims: Iterable[Shim] = SHIMS) -> str:
    lines = ["id\tstatus\tpath\tcanonical_path\tremoval"]
    for shim in shims:
        lines.append(
            f"{shim.shim_id}\t{shim.status}\t{shim.path}\t{shim.canonical_path}\t{shim.removal}"
        )
    return "\n".join(lines)


def main() -> int:
    violations = collect_violations(REPO_ROOT, require_roots=True)
    print(render_table())
    if not violations:
        print("compat shim inventory: ok")
        return 0
    print("compat shim inventory violations:", file=sys.stderr)
    for item in violations:
        print(f"- {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
