"""Fail-closed policy evaluation for repository auto-merge candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable, Sequence

from .automerge_evidence import (
    evidence_complete,
    required_names,
    stability_elapsed,
    summarize_evidence,
)
from .automerge_model import (
    AutoMergePolicy,
    CandidateClass,
    CandidateSnapshot,
    DecisionKind,
    GateRequirement,
    GateResult,
    MergeAction,
    MergeDecision,
    RiskTier,
    StackRelation,
)


DEFAULT_REQUIRED_WORKFLOWS = (
    GateRequirement("CI/CD"),
    GateRequirement("Merge Readiness"),
    GateRequirement("Secret scanning"),
    GateRequirement("Malware Gate"),
    GateRequirement("Repository Hygiene Gate"),
    GateRequirement("Artifact Policy"),
    GateRequirement("Provenance Policy"),
    GateRequirement("PR Hygiene"),
)

SECURITY_WORKFLOWS = (
    GateRequirement("Workflow Input Security"),
    GateRequirement("Dependency Security"),
    GateRequirement("Dependency Review"),
)

CODE_WORKFLOWS = (
    GateRequirement("Backend Quality"),
    GateRequirement("Frontier Contracts"),
    GateRequirement("ARM64 Ubuntu Validation"),
)

DEPENDENCY_FILENAMES = frozenset(
    {
        "pyproject.toml",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "gradle.lockfile",
    }
)

CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "skeleton/",
    "scripts/",
    "tests/",
)

DOC_PREFIXES = (
    "docs/",
    "README",
    "CHANGELOG",
)

SECURITY_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".github/dependabot",
    ".gitleaks",
    ".semgrep",
    "security/",
    "skeleton/security/",
    "skeleton/pr_automation/",
)

RELEASE_PREFIXES = (
    "Dockerfile",
    "docker/",
    "deploy/",
    "helm/",
    "k8s/",
    "release/",
    ".github/workflows/reproducible-release",
)

LOW_RISK_SUFFIXES = (
    ".md",
    ".rst",
    ".txt",
)


@dataclass(frozen=True, slots=True)
class PathClassification:
    dependency: bool
    code: bool
    docs_only: bool
    security: bool
    release: bool
    workflow: bool
    test_only: bool
    sensitive: tuple[str, ...]
    critical: tuple[str, ...]
    risk: RiskTier


def canonical_path(path: str) -> str | None:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        return None
    pure = PurePosixPath(path)
    normalized = pure.as_posix()
    if pure.is_absolute() or normalized != path:
        return None
    if any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return normalized


def _starts(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _is_dependency(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in DEPENDENCY_FILENAMES:
        return True
    lowered = name.casefold()
    return lowered.startswith("requirements") and lowered.endswith(".txt")


def _is_test(path: str) -> bool:
    name = PurePosixPath(path).name
    return (
        path.startswith("tests/")
        or path.startswith("skeleton/testing/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _is_doc(path: str) -> bool:
    return _starts(path, DOC_PREFIXES) or path.endswith(LOW_RISK_SUFFIXES)


def classify_paths(
    files: Sequence[str],
    policy: AutoMergePolicy,
) -> PathClassification:
    normalized: list[str] = []
    invalid: list[str] = []
    for raw in files:
        path = canonical_path(raw)
        if path is None:
            invalid.append(str(raw))
        else:
            normalized.append(path)

    sensitive = tuple(
        path
        for path in normalized
        if any(path == prefix or path.startswith(prefix) for prefix in policy.sensitive_prefixes)
    )
    critical = tuple(
        path
        for path in normalized
        if any(path == prefix or path.startswith(prefix) for prefix in policy.critical_prefixes)
    )
    if invalid:
        critical = (*critical, *tuple(f"<invalid:{item}>" for item in invalid))

    dependency = bool(normalized) and any(_is_dependency(path) for path in normalized)
    workflow = any(path.startswith(".github/workflows/") for path in normalized)
    security = any(_starts(path, SECURITY_PREFIXES) for path in normalized)
    release = any(_starts(path, RELEASE_PREFIXES) for path in normalized)
    code = any(_starts(path, CODE_PREFIXES) for path in normalized)
    docs_only = bool(normalized) and all(_is_doc(path) for path in normalized)
    test_only = bool(normalized) and all(_is_test(path) or _is_doc(path) for path in normalized) and any(
        _is_test(path) for path in normalized
    )

    if critical or workflow or security:
        risk = RiskTier.CRITICAL
    elif release or dependency:
        risk = RiskTier.HIGH
    elif code and not test_only:
        risk = RiskTier.MEDIUM
    else:
        risk = RiskTier.LOW

    return PathClassification(
        dependency=dependency,
        code=code,
        docs_only=docs_only,
        security=security,
        release=release,
        workflow=workflow,
        test_only=test_only,
        sensitive=tuple(sorted(set(sensitive))),
        critical=tuple(sorted(set(critical))),
        risk=risk,
    )


def classify_candidate(snapshot: CandidateSnapshot, policy: AutoMergePolicy) -> CandidateClass:
    author = snapshot.identity.author.casefold()
    if author in set(policy.owner_logins):
        return CandidateClass.OWNER
    if author == "dependabot[bot]":
        return CandidateClass.DEPENDABOT
    if author in set(policy.trusted_bot_logins):
        return CandidateClass.BOT
    return CandidateClass.UNKNOWN


def requirements_for_candidate(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
) -> tuple[GateRequirement, ...]:
    classification = classify_paths(snapshot.diff.files, policy)
    requirements: list[GateRequirement] = [
        *DEFAULT_REQUIRED_WORKFLOWS,
        *policy.required_workflows,
    ]

    if classification.code:
        requirements.extend(CODE_WORKFLOWS)
    if classification.dependency:
        requirements.extend(
            (
                GateRequirement("Dependency Review"),
                GateRequirement("Dependency Security"),
            )
        )
    if classification.security or classification.workflow:
        requirements.extend(SECURITY_WORKFLOWS)
    if classification.release:
        requirements.append(GateRequirement("Reproducible Release"))

    deduped: dict[str, GateRequirement] = {}
    for requirement in requirements:
        prior = deduped.get(requirement.name)
        if prior is None:
            deduped[requirement.name] = requirement
            continue
        deduped[requirement.name] = GateRequirement(
            requirement.name,
            allow_skipped=prior.allow_skipped and requirement.allow_skipped,
            require_pull_request_event=(
                prior.require_pull_request_event or requirement.require_pull_request_event
            ),
        )
    return tuple(deduped.values())


def _labels(snapshot: CandidateSnapshot) -> set[str]:
    return {label.casefold() for label in snapshot.labels}


def candidate_opted_in(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
    candidate_class: CandidateClass,
) -> bool:
    labels = _labels(snapshot)
    if labels.intersection(policy.opt_out_labels):
        return False
    if labels.intersection(policy.opt_in_labels):
        return True
    if candidate_class is CandidateClass.OWNER:
        return policy.allow_owner_without_opt_in
    if candidate_class is CandidateClass.DEPENDABOT:
        return policy.allow_dependabot_without_opt_in
    return False


def _hold(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
    reasons: Iterable[str],
    gates: Sequence[GateResult] = (),
    *,
    risk: RiskTier | None = None,
) -> MergeDecision:
    return MergeDecision(
        pr_number=snapshot.identity.number,
        kind=DecisionKind.HOLD,
        reasons=tuple(reasons),
        gates=tuple(gates),
        actions=(),
        snapshot_fingerprint=snapshot.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
        risk_tier=risk or snapshot.risk_tier,
    )


def _ignore(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
    *reasons: str,
) -> MergeDecision:
    return MergeDecision(
        pr_number=snapshot.identity.number,
        kind=DecisionKind.IGNORE,
        reasons=tuple(reasons),
        gates=(),
        actions=(),
        snapshot_fingerprint=snapshot.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
        risk_tier=snapshot.risk_tier,
    )


def _ready(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
    gates: Sequence[GateResult],
    *,
    risk: RiskTier,
    action_kind: DecisionKind,
    reason: str,
) -> MergeDecision:
    action = MergeAction.make(
        kind=action_kind,
        snapshot=snapshot,
        merge_method=policy.merge_method,
        reason=reason,
    )
    return MergeDecision(
        pr_number=snapshot.identity.number,
        kind=action_kind,
        reasons=(reason,),
        gates=tuple(gates),
        actions=(action,),
        snapshot_fingerprint=snapshot.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
        risk_tier=risk,
    )


def _identity_reasons(snapshot: CandidateSnapshot, policy: AutoMergePolicy) -> list[str]:
    identity = snapshot.identity
    reasons: list[str] = []

    if identity.state.casefold() != "open":
        reasons.append("pull_request_not_open")
    if identity.draft:
        reasons.append("pull_request_is_draft")
    if identity.mergeable is not True:
        reasons.append("mergeability_not_affirmatively_true")
    if identity.mergeable_state.casefold() not in {"clean", "unstable"}:
        reasons.append(f"mergeable_state:{identity.mergeable_state or 'unknown'}")
    if policy.same_repository_only and identity.from_fork:
        reasons.append("fork_head_not_allowed")
    if snapshot.head_contains_base is not True:
        reasons.append("head_does_not_contain_current_base")
    if snapshot.diff.changed_files == 0:
        reasons.append("empty_diff")
    if snapshot.diff.changed_files > policy.budget.max_changed_files:
        reasons.append("changed_file_budget_exceeded")
    if snapshot.diff.line_delta > policy.budget.max_line_delta:
        reasons.append("line_delta_budget_exceeded")

    return reasons


def _stack_reasons(snapshot: CandidateSnapshot, policy: AutoMergePolicy) -> list[str]:
    if snapshot.stack_relation is StackRelation.CYCLE:
        return ["stack_cycle"]
    if snapshot.stack_relation is StackRelation.ORPHAN:
        return ["stack_parent_missing"]
    if snapshot.stack_relation is StackRelation.CHILD:
        if not policy.allow_stack_child_merge:
            return ["stack_child_merge_disabled"]
        if snapshot.parent_pr is None:
            return ["stack_child_missing_parent_identity"]
        if snapshot.identity.base_ref == policy.default_branch:
            return ["stack_child_relation_mismatch"]
    return []


def evaluate_candidate(
    snapshot: CandidateSnapshot,
    policy: AutoMergePolicy,
    *,
    now: datetime | None = None,
) -> MergeDecision:
    identity = snapshot.identity
    classification = classify_paths(snapshot.diff.files, policy)
    candidate_class = classify_candidate(snapshot, policy)

    if identity.state.casefold() != "open":
        return _ignore(snapshot, policy, "pull_request_not_open")

    identity_reasons = _identity_reasons(snapshot, policy)
    if identity_reasons:
        return _hold(snapshot, policy, identity_reasons, risk=classification.risk)

    stack_reasons = _stack_reasons(snapshot, policy)
    if stack_reasons:
        return _hold(snapshot, policy, stack_reasons, risk=classification.risk)

    if candidate_class is CandidateClass.UNKNOWN:
        return _hold(
            snapshot,
            policy,
            ("untrusted_author_class",),
            risk=classification.risk,
        )

    labels = _labels(snapshot)
    if labels.intersection(policy.opt_out_labels):
        return _hold(snapshot, policy, ("explicit_automerge_opt_out",), risk=classification.risk)

    if not candidate_opted_in(snapshot, policy, candidate_class):
        return _hold(snapshot, policy, ("automerge_opt_in_missing",), risk=classification.risk)

    requirements = requirements_for_candidate(snapshot, policy)
    evidence = summarize_evidence(
        runs=snapshot.workflow_runs,
        requirements=requirements,
        head_sha=identity.head_sha,
        reviews=snapshot.reviews,
        unresolved_threads=snapshot.unresolved_threads,
    )
    complete, evidence_reasons = evidence_complete(
        evidence,
        required_approvals=policy.required_approvals,
        require_no_changes_requested=policy.require_no_changes_requested,
        require_resolved_threads=policy.require_resolved_threads,
    )
    if not complete:
        return _hold(
            snapshot,
            policy,
            evidence_reasons,
            evidence.gates,
            risk=classification.risk,
        )

    moment = now or datetime.now(timezone.utc)
    if not stability_elapsed(
        snapshot.workflow_runs,
        head_sha=identity.head_sha,
        required_names=required_names(requirements),
        now=moment,
        stability_seconds=policy.budget.stability_seconds,
    ):
        return _hold(
            snapshot,
            policy,
            ("exact_head_success_stability_window_not_elapsed",),
            evidence.gates,
            risk=classification.risk,
        )

    if snapshot.stack_relation is StackRelation.CHILD:
        return _ready(
            snapshot,
            policy,
            evidence.gates,
            risk=classification.risk,
            action_kind=DecisionKind.MERGE_STACK_CHILD,
            reason="all stack-child merge gates satisfied on exact immutable head",
        )

    if identity.base_ref != policy.default_branch:
        return _hold(
            snapshot,
            policy,
            (f"root_candidate_wrong_base:{identity.base_ref}",),
            evidence.gates,
            risk=classification.risk,
        )

    if policy.mode.value == "observe":
        return MergeDecision(
            pr_number=identity.number,
            kind=DecisionKind.READY,
            reasons=("all merge gates satisfied; observe mode forbids mutation",),
            gates=evidence.gates,
            actions=(),
            snapshot_fingerprint=snapshot.fingerprint(),
            policy_fingerprint=policy.fingerprint(),
            risk_tier=classification.risk,
        )

    action_kind = (
        DecisionKind.ENABLE_AUTO_MERGE
        if policy.mode.value == "enable_native"
        else DecisionKind.MERGE
    )
    return _ready(
        snapshot,
        policy,
        evidence.gates,
        risk=classification.risk,
        action_kind=action_kind,
        reason="all root merge gates satisfied on exact immutable head",
    )


def sort_decisions_for_execution(
    decisions: Iterable[MergeDecision],
) -> tuple[MergeDecision, ...]:
    rank = {
        DecisionKind.MERGE_STACK_CHILD: 0,
        DecisionKind.ENABLE_AUTO_MERGE: 1,
        DecisionKind.MERGE: 1,
        DecisionKind.READY: 2,
        DecisionKind.HOLD: 3,
        DecisionKind.IGNORE: 4,
    }
    risk_rank = {
        RiskTier.LOW: 0,
        RiskTier.MEDIUM: 1,
        RiskTier.HIGH: 2,
        RiskTier.CRITICAL: 3,
    }
    return tuple(
        sorted(
            decisions,
            key=lambda item: (
                rank[item.kind],
                risk_rank[item.risk_tier],
                item.pr_number,
            ),
        )
    )


def mutating_decisions(
    decisions: Iterable[MergeDecision],
) -> tuple[MergeDecision, ...]:
    return tuple(item for item in decisions if item.actions)


__all__ = [
    "CODE_WORKFLOWS",
    "DEFAULT_REQUIRED_WORKFLOWS",
    "DEPENDENCY_FILENAMES",
    "PathClassification",
    "SECURITY_WORKFLOWS",
    "candidate_opted_in",
    "canonical_path",
    "classify_candidate",
    "classify_paths",
    "evaluate_candidate",
    "mutating_decisions",
    "requirements_for_candidate",
    "sort_decisions_for_execution",
]
