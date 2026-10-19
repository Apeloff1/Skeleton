"""Host-bound execution plane for the 100 Jeeves assurance milestones.

Every catalog milestone has a different quantitative acceptance measurement.
The workbench performs real comparison, independent sampling, source binding,
dependency scheduling, recorded blocking, and replay. It cannot manufacture
host measurements. Missing, contradictory, stale or unscoped measurements
return a blocked result and never elevate a milestone to "completed".
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence

from .delivery_assurance_milestones import (
    ASSURANCE_MILESTONES, MilestoneAttestation, MilestoneBoard,
    MilestoneEvidenceError, MILESTONE_INDEX, verify_milestone_board,
)
from .types import stable_fingerprint

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class WorkbenchError(ValueError):
    """The requested milestone has no sufficient validated host evidence."""


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    milestone_id: str
    metric: str
    unit: str
    comparison: str
    target: float
    min_samples: int
    max_disagreement: float = 0.0

    def __post_init__(self) -> None:
        if self.milestone_id not in MILESTONE_INDEX:
            raise WorkbenchError("acceptance target is not in the 100-milestone catalog")
        if not _NAME.fullmatch(self.metric) or not self.unit.strip():
            raise WorkbenchError("acceptance metric requires stable name and unit")
        if self.comparison not in {"at_least", "at_most", "exact"}:
            raise WorkbenchError("unsupported acceptance comparator")
        if not isinstance(self.target, (int, float)) or isinstance(self.target, bool) or not math.isfinite(self.target):
            raise WorkbenchError("acceptance target must be finite")
        if type(self.min_samples) is not int or self.min_samples <= 0:
            raise WorkbenchError("acceptance needs positive sample count")
        if not isinstance(self.max_disagreement, (int, float)) or not math.isfinite(self.max_disagreement) or self.max_disagreement < 0:
            raise WorkbenchError("invalid independent-verifier disagreement budget")

    def accepts(self, value: float) -> bool:
        if self.comparison == "at_least":
            return value >= self.target
        if self.comparison == "at_most":
            return value <= self.target
        return value == self.target


# Ten separately named and measurable acceptance criteria per domain. They
# are deliberately explicit: a generic pass flag cannot satisfy all of them.
# Fields: name, unit, comparator, target, minimum sample count, disagreement.
_CRITERIA = {
    "context": (
        ("scoped_negative_queries", "queries", "at_least", 5, 5, 0),
        ("pages_with_verified_termination", "ratio", "exact", 1, 3, 0),
        ("failed_searches_falsely_compacted", "count", "exact", 0, 10, 0),
        ("retained_results_with_valid_hashes", "ratio", "exact", 1, 10, 0),
        ("evidence_metadata_mutation_escapes", "count", "exact", 0, 8, 0),
        ("goal_policy_mutations_rejected", "ratio", "exact", 1, 6, 0),
        ("retained_note_replay_success", "ratio", "exact", 1, 8, 0),
        ("refill_memory_limit_violations", "count", "exact", 0, 8, 0),
        ("compaction_accounting_errors", "count", "exact", 0, 5, 0),
        ("page_replay_hash_match", "ratio", "exact", 1, 5, 0),
    ),
    "verifier": (
        ("independent_integrity_cases", "cases", "at_least", 10, 10, 0),
        ("independent_scope_cases", "cases", "at_least", 10, 10, 0),
        ("goal_mutations_rejected", "ratio", "exact", 1, 10, 0),
        ("result_mutations_rejected", "ratio", "exact", 1, 10, 0),
        ("evidence_mutations_rejected", "ratio", "exact", 1, 10, 0),
        ("duplicate_source_mutations_rejected", "ratio", "exact", 1, 10, 0),
        ("scope_inflation_rejected", "ratio", "exact", 1, 10, 0),
        ("false_global_absence_rejected", "ratio", "exact", 1, 10, 0),
        ("adversarial_attack_rejections", "ratio", "exact", 1, 20, 0),
        ("verifier_replay_mismatches", "count", "exact", 0, 10, 0),
    ),
    "code": (
        ("syntax_errors_remaining", "count", "exact", 0, 10, 0),
        ("lint_errors_remaining", "count", "exact", 0, 10, 0),
        ("type_errors_remaining", "count", "exact", 0, 10, 0),
        ("unresolved_imports", "count", "exact", 0, 10, 0),
        ("unclassified_error_matches", "count", "exact", 0, 10, 0),
        ("unauthorized_repairs", "count", "exact", 0, 10, 0),
        ("repairs_missing_recheck", "count", "exact", 0, 10, 0),
        ("modularity_violations", "count", "exact", 0, 10, 0),
        ("performance_regression_pct", "percent", "at_most", 0, 10, 0.01),
        ("reused_checker_evidence", "count", "exact", 0, 10, 0),
    ),
    "game": (
        ("engine_integration_failures", "count", "exact", 0, 10, 0),
        ("unresolved_asset_references", "count", "exact", 0, 10, 0),
        ("broken_animation_states", "count", "exact", 0, 10, 0),
        ("physics_divergence_pct", "percent", "at_most", 0.1, 10, 0.01),
        ("frame_continuity_breaks", "count", "exact", 0, 10, 0),
        ("controller_mapping_conflicts", "count", "exact", 0, 10, 0),
        ("quest_state_contradictions", "count", "exact", 0, 10, 0),
        ("full_native_playthrough_coverage", "ratio", "exact", 1, 10, 0),
        ("runtime_frame_budget_misses", "count", "exact", 0, 10, 0),
        ("platform_export_failures", "count", "exact", 0, 10, 0),
    ),
    "measurement": (
        ("baseline_without_source_ref", "count", "exact", 0, 5, 0),
        ("unequal_measurement_methods", "count", "exact", 0, 5, 0),
        ("incompatible_metric_units", "count", "exact", 0, 5, 0),
        ("independent_sample_count", "samples", "at_least", 30, 30, 0),
        ("nonfinite_measurements", "count", "exact", 0, 10, 0),
        ("unmet_objective_targets", "count", "exact", 0, 10, 0),
        ("unapproved_regressions", "count", "exact", 0, 10, 0),
        ("performance_variance_pct", "percent", "at_most", 5, 30, 1),
        ("comparative_score_method_coverage", "ratio", "exact", 1, 10, 0),
        ("measurement_replay_failures", "count", "exact", 0, 10, 0),
    ),
    "rights": (
        ("uninventoried_artifacts", "count", "exact", 0, 10, 0),
        ("unsafe_artifact_paths", "count", "exact", 0, 10, 0),
        ("original_assets_without_proof", "count", "exact", 0, 10, 0),
        ("missing_external_attributions", "count", "exact", 0, 10, 0),
        ("unsatisfied_license_conditions", "count", "exact", 0, 10, 0),
        ("undocumented_public_domain_claims", "count", "exact", 0, 10, 0),
        ("derivative_works_missing_permissions", "count", "exact", 0, 10, 0),
        ("unresolved_similarity_findings", "count", "exact", 0, 10, 0),
        ("unknown_rights_admitted", "count", "exact", 0, 10, 0),
        ("unscoped_rights_checks", "count", "exact", 0, 10, 0),
    ),
    "creative": (
        ("unresolved_originality_findings", "count", "exact", 0, 10, 0),
        ("cosmetic_only_rewrites_admitted", "count", "exact", 0, 10, 0),
        ("author_voice_breaks", "count", "exact", 0, 10, 0),
        ("gdd_canon_violations", "count", "exact", 0, 10, 0),
        ("unresolved_story_contradictions", "count", "exact", 0, 10, 0),
        ("character_arc_continuity_errors", "count", "exact", 0, 10, 0),
        ("dialogue_continuity_errors", "count", "exact", 0, 10, 0),
        ("mechanic_story_disagreements", "count", "exact", 0, 10, 0),
        ("nonindependent_content_reviews", "count", "exact", 0, 10, 0),
        ("misordered_final_review_stages", "count", "exact", 0, 10, 0),
    ),
    "receipts": (
        ("source_digest_mismatches", "count", "exact", 0, 10, 0),
        ("working_serial_violations", "count", "exact", 0, 10, 0),
        ("scrutiny_serial_violations", "count", "exact", 0, 10, 0),
        ("final_serial_violations", "count", "exact", 0, 10, 0),
        ("journal_serial_violations", "count", "exact", 0, 10, 0),
        ("receipt_chain_breaks", "count", "exact", 0, 10, 0),
        ("source_snapshot_drift", "count", "exact", 0, 10, 0),
        ("receipt_replay_errors", "count", "exact", 0, 10, 0),
        ("tamper_cases_undetected", "count", "exact", 0, 10, 0),
        ("exported_raw_source_leaks", "count", "exact", 0, 10, 0),
    ),
    "operations": (
        ("checkpoint_integrity_failures", "count", "exact", 0, 10, 0),
        ("resume_state_mismatches", "count", "exact", 0, 10, 0),
        ("uncancelled_work_after_stop", "count", "exact", 0, 10, 0),
        ("crash_replay_errors", "count", "exact", 0, 10, 0),
        ("unbounded_resource_exceptions", "count", "exact", 0, 10, 0),
        ("cross_run_data_leaks", "count", "exact", 0, 10, 0),
        ("lease_double_owners", "count", "exact", 0, 10, 0),
        ("non_idempotent_replays", "count", "exact", 0, 10, 0),
        ("long_run_trace_gaps", "count", "exact", 0, 10, 0),
        ("retention_policy_violations", "count", "exact", 0, 10, 0),
    ),
    "release": (
        ("unreviewed_answer_bytes", "count", "exact", 0, 10, 0),
        ("release_source_drift", "count", "exact", 0, 10, 0),
        ("omitted_user_quality_requirements", "count", "exact", 0, 10, 0),
        ("unverified_independent_decisions", "count", "exact", 0, 10, 0),
        ("missing_host_artifact_proofs", "count", "exact", 0, 10, 0),
        ("non_green_exact_head_gates", "count", "exact", 0, 10, 0),
        ("first_install_failures", "count", "exact", 0, 10, 0),
        ("rollback_validation_failures", "count", "exact", 0, 10, 0),
        ("unauthorized_merge_attempts", "count", "exact", 0, 10, 0),
        ("production_admission_violations", "count", "exact", 0, 10, 0),
    ),
}


def _build_acceptance() -> tuple[AcceptanceCriterion, ...]:
    rows: list[AcceptanceCriterion] = []
    for index, milestone in enumerate(ASSURANCE_MILESTONES):
        row = _CRITERIA[milestone.domain][index % 10]
        rows.append(AcceptanceCriterion(milestone.code, *row))
    if len(rows) != 100 or len({row.metric for row in rows}) != 100:
        raise WorkbenchError("100 acceptance checks must use unique measurements")
    return tuple(rows)


ACCEPTANCE_CRITERIA = _build_acceptance()
CRITERION_BY_ID = {row.milestone_id: row for row in ACCEPTANCE_CRITERIA}


@dataclass(frozen=True, slots=True)
class HostMeasurement:
    """Scoped, immutable measurement produced by a host checker."""

    milestone_id: str
    checker_id: str
    source_commit: str
    artifact_digest: str
    metric: str
    unit: str
    observed: float
    sample_count: int
    method: str
    evidence_ref: str
    scope: str

    def __post_init__(self) -> None:
        if self.milestone_id not in CRITERION_BY_ID:
            raise WorkbenchError("unknown acceptance metric")
        if not isinstance(self.checker_id, str) or not _NAME.fullmatch(self.checker_id):
            raise WorkbenchError("invalid host checker identity")
        if not isinstance(self.source_commit, str) or not _SHA1.fullmatch(self.source_commit):
            raise WorkbenchError("measurement must pin a 40-digit commit")
        if not isinstance(self.artifact_digest, str) or not _SHA256.fullmatch(self.artifact_digest):
            raise WorkbenchError("measurement must pin source bytes")
        if not isinstance(self.metric, str) or not isinstance(self.unit, str):
            raise WorkbenchError("invalid measurement type")
        if isinstance(self.observed, bool) or not isinstance(self.observed, (int, float)) or not math.isfinite(self.observed):
            raise WorkbenchError("nonfinite host measurement")
        if type(self.sample_count) is not int or self.sample_count < 1:
            raise WorkbenchError("host measurement needs an actual positive sample count")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 4096 for v in (
            self.method, self.evidence_ref, self.scope,
        )):
            raise WorkbenchError("host measurement lacks bounded method, scope or evidence")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "milestone": self.milestone_id, "checker": self.checker_id,
            "commit": self.source_commit, "artifact": self.artifact_digest,
            "metric": self.metric, "unit": self.unit,
            "observed": self.observed, "samples": self.sample_count,
            "method": self.method, "evidence": self.evidence_ref,
            "scope": self.scope,
        })


@dataclass(frozen=True, slots=True)
class ExecutionVerdict:
    milestone_id: str
    result: str
    detail: str
    primary_digest: str | None
    independent_digest: str | None
    attestation: MilestoneAttestation | None

    @property
    def passed(self) -> bool:
        return self.result == "pass"

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "milestone": self.milestone_id, "result": self.result,
            "detail": self.detail, "primary": self.primary_digest,
            "independent": self.independent_digest,
            "attestation": self.attestation.fingerprint if self.attestation else None,
        })


HostChecker = Callable[[AcceptanceCriterion, str, str], HostMeasurement]


def evaluate_milestone(
    milestone_id: str,
    source_commit: str,
    artifact_digest: str,
    primary: HostChecker | None,
    independent: HostChecker | None,
) -> ExecutionVerdict:
    """Measure the same exact source with two independent host checkers.

    Missing adapters or mismatch fail closed. This intentionally does not
    claim checkers' independence merely because their names differ.
    """
    spec = CRITERION_BY_ID.get(milestone_id)
    if spec is None:
        raise WorkbenchError("milestone is not executable")
    if not isinstance(source_commit, str) or not _SHA1.fullmatch(source_commit):
        raise WorkbenchError("execution requires the exact source commit")
    if not isinstance(artifact_digest, str) or not _SHA256.fullmatch(artifact_digest):
        raise WorkbenchError("execution requires a source artifact hash")

    def blocked(reason: str, p: HostMeasurement | None = None, q: HostMeasurement | None = None) -> ExecutionVerdict:
        return ExecutionVerdict(
            milestone_id, "blocked", reason,
            p.fingerprint if p else None, q.fingerprint if q else None, None,
        )

    if not callable(primary) or not callable(independent) or primary is independent:
        return blocked("Two separately registered host checkers are required")
    p = primary(spec, source_commit, artifact_digest)
    q = independent(spec, source_commit, artifact_digest)
    if not isinstance(p, HostMeasurement) or not isinstance(q, HostMeasurement):
        return blocked("Host checker omitted typed measurement")
    for check in (p, q):
        if (check.milestone_id != milestone_id
                or check.metric != spec.metric or check.unit != spec.unit
                or check.source_commit != source_commit
                or check.artifact_digest != artifact_digest):
            return blocked("Host measurement is stale, misattributed or uses wrong units", p, q)
        if check.sample_count < spec.min_samples:
            return blocked("Insufficient samples for mandatory acceptance target", p, q)
    if (p.checker_id == q.checker_id or p.evidence_ref == q.evidence_ref):
        return blocked("Independent host measurements reuse checker identity or evidence", p, q)
    if p.method != q.method or p.scope != q.scope:
        return blocked("Host measurements have incompatible methods or scope", p, q)
    if abs(p.observed - q.observed) > spec.max_disagreement:
        return blocked("Independent host measurements disagree beyond the permitted budget", p, q)
    if not spec.accepts(p.observed) or not spec.accepts(q.observed):
        return blocked("Milestone measurement does not meet its objective target", p, q)
    attestation = MilestoneAttestation(
        milestone_id=milestone_id, source_commit=source_commit,
        artifact_digest=artifact_digest, scope=p.scope,
        primary_checker=p.checker_id, independent_checker=q.checker_id,
        primary_evidence=p.evidence_ref, independent_evidence=q.evidence_ref,
        verdict="pass",
    )
    return ExecutionVerdict(
        milestone_id, "pass", "Both measured values satisfy the scoped objective",
        p.fingerprint, q.fingerprint, attestation,
    )


@dataclass(frozen=True, slots=True)
class ExecutionBatch:
    board: MilestoneBoard
    attempts: tuple[ExecutionVerdict, ...]
    deferred: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "board": self.board.fingerprint,
            "attempts": [item.fingerprint for item in self.attempts],
            "deferred": self.deferred,
        })

    def summary(self) -> dict[str, object]:
        return {
            **self.board.summary(),
            "attempted": len(self.attempts),
            "deferred": len(self.deferred),
            "failed": len([item for item in self.attempts if not item.passed]),
            "batch_receipt": self.fingerprint,
        }


def execute_milestone_batch(
    board: MilestoneBoard,
    artifact_digest: str,
    checkers: Mapping[str, tuple[HostChecker | None, HostChecker | None]],
    *,
    requested: Sequence[str] = (),
) -> ExecutionBatch:
    """Run up to 100 criteria with per-domain dependency ordering and receipts.

    Later milestones in the same domain are deferred until their prerequisite
    is verified, not marked green because a downstream checker gave a score.
    Callers may resume the returned board on the same source commit.
    """
    verify_milestone_board(board)
    selection = tuple(dict.fromkeys(requested)) if requested else tuple(
        item.code for item in ASSURANCE_MILESTONES
    )
    if any(item not in CRITERION_BY_ID for item in selection):
        raise WorkbenchError("batch contains an unknown milestone")
    current = board
    reports: list[ExecutionVerdict] = []
    deferred: list[str] = []
    for milestone_id in selection:
        if milestone_id in current.passing or milestone_id in current.blocked:
            continue
        prerequisite = MILESTONE_INDEX[milestone_id].prerequisite
        if prerequisite is not None and prerequisite not in current.passing:
            deferred.append(milestone_id)
            continue
        primary, secondary = checkers.get(milestone_id, (None, None))
        verdict = evaluate_milestone(
            milestone_id, board.source_commit, artifact_digest, primary, secondary,
        )
        reports.append(verdict)
        if verdict.passed:
            current = current.register(verdict.attestation)
        else:
            # The board records explicit blocked claims, never fabricated
            # success. A changed assessment is a *new* source-bound attempt.
            # Blocked results do not silently lock a retry into success.
            continue
    return ExecutionBatch(current, tuple(reports), tuple(deferred))
