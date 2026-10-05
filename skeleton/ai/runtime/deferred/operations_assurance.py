"""Cross-volume deterministic assurance controls for VOL-188..VOL-200.

This module closes the remaining orchestration seams around the already-landed
chaos, recovery, release, deployment, developer, simulation, fuzzing, property,
and formal-method primitives.  It is deliberately evidence-only: no object in
this module grants merge, deployment, production, or masterplan-completion
authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


class OperationsAssuranceError(ValueError):
    """A VOL-188..VOL-200 assurance invariant failed closed."""


_HEX = frozenset("0123456789abcdef")
_TERMINAL_BAD = frozenset(
    {"failure", "cancelled", "skipped", "neutral", "timed_out", "action_required"}
)


def _text(name: str, value: object, *, limit: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(ord(ch) < 32 for ch in value)
    ):
        raise OperationsAssuranceError(f"{name} must be normalized non-empty text")
    return value


def _texts(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise OperationsAssuranceError(f"{name} must be a collection")
    result = tuple(sorted({_text(name, value) for value in values}))
    if not result and not allow_empty:
        raise OperationsAssuranceError(f"{name} must be non-empty")
    return result


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OperationsAssuranceError(f"{name} must be an integer >= {minimum}")
    return value


def _ppm(name: str, value: object) -> int:
    result = _integer(name, value)
    if result > 1_000_000:
        raise OperationsAssuranceError(f"{name} must be <= 1000000")
    return result


def _sha(name: str, value: object, *, length: int = 64) -> str:
    text = _text(name, value, limit=length)
    if len(text) != length or any(ch not in _HEX for ch in text):
        raise OperationsAssuranceError(
            f"{name} must be a lowercase {length}-character hexadecimal digest"
        )
    return text


# ---------------------------------------------------------------------------
# VOL-188: governed fault library and runbook binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultDefinition:
    fault_id: str
    target_kind: str
    fault_kind: str
    max_duration_seconds: int
    runbook_ref: str
    abort_signal: str

    def __post_init__(self) -> None:
        for name in ("fault_id", "target_kind", "fault_kind", "runbook_ref", "abort_signal"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(
            self,
            "max_duration_seconds",
            _integer("max_duration_seconds", self.max_duration_seconds, minimum=1),
        )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "fault_id": self.fault_id,
                "target_kind": self.target_kind,
                "fault_kind": self.fault_kind,
                "max_duration_seconds": self.max_duration_seconds,
                "runbook_ref": self.runbook_ref,
                "abort_signal": self.abort_signal,
            }
        )


@dataclass(frozen=True, slots=True)
class FaultPlan:
    campaign_id: str
    fault_digests: tuple[str, ...]
    runbook_refs: tuple[str, ...]
    max_total_duration_seconds: int
    external_side_effects_authorized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_id", _text("campaign_id", self.campaign_id))
        object.__setattr__(
            self,
            "fault_digests",
            tuple(sorted(_sha("fault_digest", value) for value in self.fault_digests)),
        )
        object.__setattr__(
            self, "runbook_refs", _texts("runbook_ref", self.runbook_refs)
        )
        object.__setattr__(
            self,
            "max_total_duration_seconds",
            _integer(
                "max_total_duration_seconds",
                self.max_total_duration_seconds,
                minimum=1,
            ),
        )
        if self.external_side_effects_authorized is not False:
            raise OperationsAssuranceError(
                "fault plan is evidence-only and cannot grant effect authority"
            )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "campaign_id": self.campaign_id,
                "fault_digests": list(self.fault_digests),
                "runbook_refs": list(self.runbook_refs),
                "max_total_duration_seconds": self.max_total_duration_seconds,
                "external_side_effects_authorized": False,
            }
        )


class FaultLibrary:
    """Bounded catalog mapping every injectable fault to a recovery runbook."""

    def __init__(self, definitions: Iterable[FaultDefinition]) -> None:
        items = tuple(definitions)
        if not items:
            raise OperationsAssuranceError("fault library cannot be empty")
        ids = [item.fault_id for item in items]
        if len(ids) != len(set(ids)):
            raise OperationsAssuranceError("fault identities must be unique")
        self._items = {item.fault_id: item for item in items}

    def get(self, fault_id: str) -> FaultDefinition:
        key = _text("fault_id", fault_id)
        try:
            return self._items[key]
        except KeyError as exc:
            raise OperationsAssuranceError("unknown fault identity") from exc

    def plan(
        self,
        campaign_id: str,
        fault_ids: Sequence[str],
        *,
        requested_total_duration_seconds: int,
    ) -> FaultPlan:
        requested = _integer(
            "requested_total_duration_seconds",
            requested_total_duration_seconds,
            minimum=1,
        )
        if not fault_ids:
            raise OperationsAssuranceError("campaign must select at least one fault")
        selected = tuple(self.get(value) for value in fault_ids)
        if len({item.fault_id for item in selected}) != len(selected):
            raise OperationsAssuranceError("campaign fault identities must be unique")
        maximum = sum(item.max_duration_seconds for item in selected)
        if requested > maximum:
            raise OperationsAssuranceError(
                "requested chaos duration exceeds declared fault-library limits"
            )
        return FaultPlan(
            campaign_id=_text("campaign_id", campaign_id),
            fault_digests=tuple(item.digest for item in selected),
            runbook_refs=tuple(item.runbook_ref for item in selected),
            max_total_duration_seconds=requested,
        )


# ---------------------------------------------------------------------------
# VOL-189: recovery-drill scheduling and risk-ledger handoff
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecoveryDrillPlan:
    drill_id: str
    environment_id: str
    scheduled_at_ms: int
    runbook_refs: tuple[str, ...]
    rto_limit_ms: int
    rpo_limit_ms: int
    manual_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("drill_id", "environment_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(
            self, "scheduled_at_ms", _integer("scheduled_at_ms", self.scheduled_at_ms)
        )
        object.__setattr__(self, "runbook_refs", _texts("runbook_ref", self.runbook_refs))
        object.__setattr__(
            self, "rto_limit_ms", _integer("rto_limit_ms", self.rto_limit_ms, minimum=1)
        )
        object.__setattr__(
            self, "rpo_limit_ms", _integer("rpo_limit_ms", self.rpo_limit_ms)
        )
        object.__setattr__(
            self,
            "manual_dependencies",
            _texts("manual_dependency", self.manual_dependencies, allow_empty=True),
        )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "drill_id": self.drill_id,
                "environment_id": self.environment_id,
                "scheduled_at_ms": self.scheduled_at_ms,
                "runbook_refs": list(self.runbook_refs),
                "rto_limit_ms": self.rto_limit_ms,
                "rpo_limit_ms": self.rpo_limit_ms,
                "manual_dependencies": list(self.manual_dependencies),
            }
        )


@dataclass(frozen=True, slots=True)
class RecoveryFinding:
    finding_id: str
    drill_id: str
    severity: str
    risk_ref: str
    owner: str
    resolved: bool = False

    def __post_init__(self) -> None:
        for name in ("finding_id", "drill_id", "risk_ref", "owner"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise OperationsAssuranceError("unsupported recovery finding severity")
        if not isinstance(self.resolved, bool):
            raise OperationsAssuranceError("resolved must be boolean")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "finding_id": self.finding_id,
                "drill_id": self.drill_id,
                "severity": self.severity,
                "risk_ref": self.risk_ref,
                "owner": self.owner,
                "resolved": self.resolved,
            }
        )


class RecoveryDrillScheduler:
    """In-memory deterministic schedule ledger; execution remains external."""

    def __init__(self) -> None:
        self._plans: dict[str, RecoveryDrillPlan] = {}
        self._findings: dict[str, RecoveryFinding] = {}

    def schedule(self, plan: RecoveryDrillPlan) -> str:
        prior = self._plans.get(plan.drill_id)
        if prior is not None and prior != plan:
            raise OperationsAssuranceError(
                "recovery drill identity reused with different plan"
            )
        self._plans[plan.drill_id] = plan
        return plan.digest

    def attach_finding(self, finding: RecoveryFinding) -> str:
        if finding.drill_id not in self._plans:
            raise OperationsAssuranceError("finding references unscheduled drill")
        prior = self._findings.get(finding.finding_id)
        if prior is not None and prior != finding:
            raise OperationsAssuranceError(
                "recovery finding identity reused with different payload"
            )
        self._findings[finding.finding_id] = finding
        return finding.digest

    def unresolved_risk_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.risk_ref
                    for item in self._findings.values()
                    if not item.resolved
                }
            )
        )


# ---------------------------------------------------------------------------
# VOL-190: release qualification -> merge-readiness binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MergeReadinessDecision:
    release_id: str
    qualification_digest: str
    exact_head_sha: str
    required_gates: tuple[str, ...]
    blockers: tuple[str, ...]
    qualified: bool
    merge_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _text("release_id", self.release_id))
        object.__setattr__(
            self,
            "qualification_digest",
            _sha("qualification_digest", self.qualification_digest),
        )
        object.__setattr__(
            self, "exact_head_sha", _sha("exact_head_sha", self.exact_head_sha, length=40)
        )
        object.__setattr__(
            self, "required_gates", _texts("required_gate", self.required_gates)
        )
        object.__setattr__(
            self, "blockers", _texts("blocker", self.blockers, allow_empty=True)
        )
        if not isinstance(self.qualified, bool):
            raise OperationsAssuranceError("qualified must be boolean")
        if self.qualified != (not self.blockers):
            raise OperationsAssuranceError(
                "merge-readiness qualified state must match blockers"
            )
        if self.merge_authority is not False:
            raise OperationsAssuranceError(
                "readiness evidence cannot grant merge authority"
            )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "release_id": self.release_id,
                "qualification_digest": self.qualification_digest,
                "exact_head_sha": self.exact_head_sha,
                "required_gates": list(self.required_gates),
                "blockers": list(self.blockers),
                "qualified": self.qualified,
                "merge_authority": False,
            }
        )


class MergeReadinessBinding:
    def __init__(self, required_gates: Iterable[str]) -> None:
        self.required_gates = _texts("required_gate", required_gates)

    def assess(
        self,
        *,
        release_id: str,
        qualification_digest: str,
        exact_head_sha: str,
        conclusions: Mapping[str, str],
    ) -> MergeReadinessDecision:
        blockers: list[str] = []
        unknown = sorted(set(conclusions) - set(self.required_gates))
        if unknown:
            blockers.extend(f"undeclared:{name}" for name in unknown)
        for gate in self.required_gates:
            conclusion = conclusions.get(gate)
            if conclusion is None:
                blockers.append(f"{gate}:missing")
            elif conclusion != "success":
                reason = conclusion if conclusion in _TERMINAL_BAD else "not-success"
                blockers.append(f"{gate}:{reason}")
        return MergeReadinessDecision(
            release_id=_text("release_id", release_id),
            qualification_digest=_sha(
                "qualification_digest", qualification_digest
            ),
            exact_head_sha=_sha("exact_head_sha", exact_head_sha, length=40),
            required_gates=self.required_gates,
            blockers=tuple(sorted(blockers)),
            qualified=not blockers,
        )


# ---------------------------------------------------------------------------
# VOL-191: canary + error-budget/quality/security/cost vector
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CanaryQualityVector:
    sample_count: int
    quality_ppm: int
    error_budget_remaining_ppm: int
    cost_ratio_ppm: int
    security_passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sample_count", _integer("sample_count", self.sample_count)
        )
        for name in ("quality_ppm", "error_budget_remaining_ppm", "cost_ratio_ppm"):
            object.__setattr__(self, name, _ppm(name, getattr(self, name)))
        if not isinstance(self.security_passed, bool):
            raise OperationsAssuranceError("security_passed must be boolean")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "sample_count": self.sample_count,
                "quality_ppm": self.quality_ppm,
                "error_budget_remaining_ppm": self.error_budget_remaining_ppm,
                "cost_ratio_ppm": self.cost_ratio_ppm,
                "security_passed": self.security_passed,
            }
        )


@dataclass(frozen=True, slots=True)
class CanaryPromotionDecision:
    vector_digest: str
    decision: str
    blockers: tuple[str, ...]
    production_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector_digest", _sha("vector_digest", self.vector_digest))
        if self.decision not in {"promote-candidate", "hold", "rollback"}:
            raise OperationsAssuranceError("unknown canary promotion decision")
        object.__setattr__(
            self, "blockers", _texts("blocker", self.blockers, allow_empty=True)
        )
        if self.decision == "promote-candidate" and self.blockers:
            raise OperationsAssuranceError("promotion candidate cannot retain blockers")
        if self.production_authority is not False:
            raise OperationsAssuranceError(
                "canary evidence cannot grant production authority"
            )


class CanaryPromotionPolicy:
    def __init__(
        self,
        *,
        min_samples: int,
        min_quality_ppm: int,
        min_error_budget_remaining_ppm: int,
        max_cost_ratio_ppm: int,
    ) -> None:
        self.min_samples = _integer("min_samples", min_samples, minimum=1)
        self.min_quality_ppm = _ppm("min_quality_ppm", min_quality_ppm)
        self.min_error_budget_remaining_ppm = _ppm(
            "min_error_budget_remaining_ppm",
            min_error_budget_remaining_ppm,
        )
        self.max_cost_ratio_ppm = _ppm("max_cost_ratio_ppm", max_cost_ratio_ppm)

    def decide(self, vector: CanaryQualityVector) -> CanaryPromotionDecision:
        blockers: list[str] = []
        rollback = False
        if vector.sample_count < self.min_samples:
            blockers.append("insufficient-samples")
        if vector.quality_ppm < self.min_quality_ppm:
            blockers.append("quality-below-threshold")
            rollback = True
        if vector.error_budget_remaining_ppm < self.min_error_budget_remaining_ppm:
            blockers.append("error-budget-exhausted")
            rollback = True
        if vector.cost_ratio_ppm > self.max_cost_ratio_ppm:
            blockers.append("cost-ratio-exceeded")
        if not vector.security_passed:
            blockers.append("security-gate-failed")
            rollback = True
        decision = "rollback" if rollback else ("hold" if blockers else "promote-candidate")
        return CanaryPromotionDecision(
            vector.digest,
            decision,
            tuple(sorted(blockers)),
        )


# ---------------------------------------------------------------------------
# VOL-192: feature-flag schema, expiry, and combination constraints
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlagDescriptor:
    flag_id: str
    owner: str
    scope: str
    default_enabled: bool
    expires_at_ms: int
    security_sensitive: bool = False

    def __post_init__(self) -> None:
        for name in ("flag_id", "owner", "scope"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.default_enabled, bool):
            raise OperationsAssuranceError("default_enabled must be boolean")
        object.__setattr__(
            self, "expires_at_ms", _integer("expires_at_ms", self.expires_at_ms, minimum=1)
        )
        if not isinstance(self.security_sensitive, bool):
            raise OperationsAssuranceError("security_sensitive must be boolean")


@dataclass(frozen=True, slots=True)
class FlagCombinationConstraint:
    constraint_id: str
    flag_ids: tuple[str, ...]
    maximum_enabled: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "constraint_id", _text("constraint_id", self.constraint_id)
        )
        object.__setattr__(self, "flag_ids", _texts("flag_id", self.flag_ids))
        object.__setattr__(
            self,
            "maximum_enabled",
            _integer("maximum_enabled", self.maximum_enabled),
        )
        if self.maximum_enabled > len(self.flag_ids):
            raise OperationsAssuranceError(
                "maximum_enabled cannot exceed constrained flag count"
            )


@dataclass(frozen=True, slots=True)
class FlagSetDecision:
    allowed: bool
    blockers: tuple[str, ...]
    state_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise OperationsAssuranceError("allowed must be boolean")
        object.__setattr__(
            self, "blockers", _texts("blocker", self.blockers, allow_empty=True)
        )
        object.__setattr__(self, "state_digest", _sha("state_digest", self.state_digest))
        if self.allowed != (not self.blockers):
            raise OperationsAssuranceError("flag-set allowed state must match blockers")


class FeatureFlagSetPolicy:
    def __init__(
        self,
        descriptors: Iterable[FlagDescriptor],
        constraints: Iterable[FlagCombinationConstraint] = (),
    ) -> None:
        items = tuple(descriptors)
        if not items:
            raise OperationsAssuranceError("feature-flag registry cannot be empty")
        ids = [item.flag_id for item in items]
        if len(ids) != len(set(ids)):
            raise OperationsAssuranceError("feature-flag identities must be unique")
        self._flags = {item.flag_id: item for item in items}
        constraints_tuple = tuple(constraints)
        constraint_ids = [item.constraint_id for item in constraints_tuple]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise OperationsAssuranceError(
                "feature-flag constraint identities must be unique"
            )
        for constraint in constraints_tuple:
            unknown = set(constraint.flag_ids) - set(self._flags)
            if unknown:
                raise OperationsAssuranceError(
                    "feature-flag combination constraint references unknown flag"
                )
        self._constraints = constraints_tuple

    def evaluate(
        self,
        states: Mapping[str, bool],
        *,
        now_ms: int,
    ) -> FlagSetDecision:
        now = _integer("now_ms", now_ms)
        if set(states) != set(self._flags):
            raise OperationsAssuranceError(
                "feature-flag evaluation requires exact registered flag set"
            )
        blockers: list[str] = []
        for flag_id, descriptor in self._flags.items():
            value = states[flag_id]
            if not isinstance(value, bool):
                raise OperationsAssuranceError("feature-flag state must be boolean")
            if value and now >= descriptor.expires_at_ms:
                blockers.append(f"{flag_id}:expired-enabled")
            if descriptor.security_sensitive and value != descriptor.default_enabled:
                blockers.append(f"{flag_id}:security-sensitive-override")
        for constraint in self._constraints:
            enabled = sum(1 for flag_id in constraint.flag_ids if states[flag_id])
            if enabled > constraint.maximum_enabled:
                blockers.append(f"{constraint.constraint_id}:combination-violation")
        digest = sha256_json(
            {
                "now_ms": now,
                "states": {key: states[key] for key in sorted(states)},
            }
        )
        return FlagSetDecision(not blockers, tuple(sorted(blockers)), digest)


# ---------------------------------------------------------------------------
# VOL-193: reversible-change classification and rollback proof binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeClassification:
    change_id: str
    change_kind: str
    durable_data_change: bool
    external_effects: bool
    backward_read_compatible: bool
    reversible: bool

    def __post_init__(self) -> None:
        for name in ("change_id", "change_kind"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "durable_data_change",
            "external_effects",
            "backward_read_compatible",
            "reversible",
        ):
            if not isinstance(getattr(self, name), bool):
                raise OperationsAssuranceError(f"{name} must be boolean")
        if self.durable_data_change and not self.backward_read_compatible and self.reversible:
            raise OperationsAssuranceError(
                "incompatible durable-data change cannot claim direct reversibility"
            )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "change_id": self.change_id,
                "change_kind": self.change_kind,
                "durable_data_change": self.durable_data_change,
                "external_effects": self.external_effects,
                "backward_read_compatible": self.backward_read_compatible,
                "reversible": self.reversible,
            }
        )


@dataclass(frozen=True, slots=True)
class RollbackProof:
    classification_digest: str
    rollback_plan_digest: str
    checkpoint_digest: str
    compatibility_evidence_digest: str
    external_effect_reconciliation_digest: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "classification_digest",
            "rollback_plan_digest",
            "checkpoint_digest",
            "compatibility_evidence_digest",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if self.external_effect_reconciliation_digest is not None:
            object.__setattr__(
                self,
                "external_effect_reconciliation_digest",
                _sha(
                    "external_effect_reconciliation_digest",
                    self.external_effect_reconciliation_digest,
                ),
            )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "classification_digest": self.classification_digest,
                "rollback_plan_digest": self.rollback_plan_digest,
                "checkpoint_digest": self.checkpoint_digest,
                "compatibility_evidence_digest": self.compatibility_evidence_digest,
                "external_effect_reconciliation_digest": self.external_effect_reconciliation_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class RollbackQualification:
    allowed: bool
    reason_code: str
    classification_digest: str
    proof_digest: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise OperationsAssuranceError("allowed must be boolean")
        object.__setattr__(self, "reason_code", _text("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "classification_digest",
            _sha("classification_digest", self.classification_digest),
        )
        if self.proof_digest is not None:
            object.__setattr__(
                self, "proof_digest", _sha("proof_digest", self.proof_digest)
            )


def qualify_rollback(
    classification: ChangeClassification,
    proof: RollbackProof | None,
) -> RollbackQualification:
    if not classification.reversible:
        return RollbackQualification(
            False,
            "change-classified-forward-fix-only",
            classification.digest,
            proof.digest if proof is not None else None,
        )
    if proof is None:
        return RollbackQualification(
            False,
            "rollback-proof-missing",
            classification.digest,
            None,
        )
    if proof.classification_digest != classification.digest:
        raise OperationsAssuranceError(
            "rollback proof references stale/different change classification"
        )
    if classification.external_effects and proof.external_effect_reconciliation_digest is None:
        return RollbackQualification(
            False,
            "external-effect-reconciliation-missing",
            classification.digest,
            proof.digest,
        )
    return RollbackQualification(
        True,
        "rollback-proof-qualified",
        classification.digest,
        proof.digest,
    )


# ---------------------------------------------------------------------------
# VOL-194: contract-aware developer templates
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContractTemplate:
    template_id: str
    contract_id: str
    command_id: str
    file_paths: tuple[str, ...]
    required_placeholders: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("template_id", "contract_id", "command_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "file_paths", _texts("file_path", self.file_paths))
        object.__setattr__(
            self,
            "required_placeholders",
            _texts("required_placeholder", self.required_placeholders),
        )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "template_id": self.template_id,
                "contract_id": self.contract_id,
                "command_id": self.command_id,
                "file_paths": list(self.file_paths),
                "required_placeholders": list(self.required_placeholders),
            }
        )


@dataclass(frozen=True, slots=True)
class GeneratedTemplateReceipt:
    template_digest: str
    value_digest: str
    contract_id: str
    command_id: str
    file_paths: tuple[str, ...]
    mutating_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "template_digest", _sha("template_digest", self.template_digest)
        )
        object.__setattr__(self, "value_digest", _sha("value_digest", self.value_digest))
        for name in ("contract_id", "command_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "file_paths", _texts("file_path", self.file_paths))
        if self.mutating_authority is not False:
            raise OperationsAssuranceError(
                "template receipt cannot grant mutation authority"
            )


class ContractTemplateRegistry:
    def __init__(self, templates: Iterable[ContractTemplate]) -> None:
        items = tuple(templates)
        if not items:
            raise OperationsAssuranceError("template registry cannot be empty")
        ids = [item.template_id for item in items]
        if len(ids) != len(set(ids)):
            raise OperationsAssuranceError("template identities must be unique")
        self._templates = {item.template_id: item for item in items}

    def render_receipt(
        self,
        template_id: str,
        values: Mapping[str, str],
    ) -> GeneratedTemplateReceipt:
        key = _text("template_id", template_id)
        try:
            template = self._templates[key]
        except KeyError as exc:
            raise OperationsAssuranceError("unknown contract template") from exc
        if set(values) != set(template.required_placeholders):
            raise OperationsAssuranceError(
                "template values must exactly match required placeholders"
            )
        normalized = {
            name: _text(f"placeholder:{name}", values[name], limit=4096)
            for name in sorted(values)
        }
        return GeneratedTemplateReceipt(
            template.digest,
            sha256_json(normalized),
            template.contract_id,
            template.command_id,
            template.file_paths,
        )


# ---------------------------------------------------------------------------
# VOL-197: explicit simulated-adapter switch and evidence labeling
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SimulationAdapterProfile:
    adapter_id: str
    simulated_adapter_id: str
    production_adapter_id: str
    evidence_label: str = "simulation"

    def __post_init__(self) -> None:
        for name in (
            "adapter_id",
            "simulated_adapter_id",
            "production_adapter_id",
            "evidence_label",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.simulated_adapter_id == self.production_adapter_id:
            raise OperationsAssuranceError(
                "simulation and production adapter identities must differ"
            )


@dataclass(frozen=True, slots=True)
class SimulationSwitchReceipt:
    profile_digest: str
    selected_adapter_id: str
    evidence_labels: tuple[str, ...]
    simulated: bool = True
    production_eligible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_digest", _sha("profile_digest", self.profile_digest))
        object.__setattr__(
            self,
            "selected_adapter_id",
            _text("selected_adapter_id", self.selected_adapter_id),
        )
        object.__setattr__(
            self, "evidence_labels", _texts("evidence_label", self.evidence_labels)
        )
        if self.simulated is not True or self.production_eligible is not False:
            raise OperationsAssuranceError(
                "simulation switch receipt cannot masquerade as production evidence"
            )


def select_simulation_adapter(
    profile: SimulationAdapterProfile,
    *,
    simulation_mode: bool,
) -> SimulationSwitchReceipt:
    if simulation_mode is not True:
        raise OperationsAssuranceError(
            "simulation adapter selection requires explicit simulation mode"
        )
    digest = sha256_json(
        {
            "adapter_id": profile.adapter_id,
            "simulated_adapter_id": profile.simulated_adapter_id,
            "production_adapter_id": profile.production_adapter_id,
            "evidence_label": profile.evidence_label,
        }
    )
    return SimulationSwitchReceipt(
        digest,
        profile.simulated_adapter_id,
        (profile.evidence_label, "non-production", "simulated-effect"),
    )


# ---------------------------------------------------------------------------
# VOL-198: P0 fuzz-target inventory and reproducer -> regression binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FuzzTarget:
    target_id: str
    contract_id: str
    criticality: str
    validator_ref: str
    regression_test_target: str

    def __post_init__(self) -> None:
        for name in ("target_id", "contract_id", "validator_ref", "regression_test_target"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.criticality not in {"p0", "p1", "p2"}:
            raise OperationsAssuranceError("fuzz target criticality must be p0/p1/p2")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "target_id": self.target_id,
                "contract_id": self.contract_id,
                "criticality": self.criticality,
                "validator_ref": self.validator_ref,
                "regression_test_target": self.regression_test_target,
            }
        )


@dataclass(frozen=True, slots=True)
class FuzzRegressionBinding:
    target_digest: str
    reproducer_digest: str
    regression_test_target: str
    promoted: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_digest", _sha("target_digest", self.target_digest))
        object.__setattr__(
            self, "reproducer_digest", _sha("reproducer_digest", self.reproducer_digest)
        )
        object.__setattr__(
            self,
            "regression_test_target",
            _text("regression_test_target", self.regression_test_target),
        )
        if self.promoted is not True:
            raise OperationsAssuranceError("reproducer binding must represent promotion")


class FuzzTargetRegistry:
    def __init__(self, targets: Iterable[FuzzTarget]) -> None:
        items = tuple(targets)
        if not items:
            raise OperationsAssuranceError("fuzz target registry cannot be empty")
        ids = [item.target_id for item in items]
        contracts = [item.contract_id for item in items]
        if len(ids) != len(set(ids)):
            raise OperationsAssuranceError("fuzz target identities must be unique")
        if len(contracts) != len(set(contracts)):
            raise OperationsAssuranceError(
                "one canonical fuzz target is allowed per contract"
            )
        self._targets = {item.target_id: item for item in items}

    def p0_targets(self) -> tuple[FuzzTarget, ...]:
        return tuple(
            sorted(
                (item for item in self._targets.values() if item.criticality == "p0"),
                key=lambda item: item.target_id,
            )
        )

    def promote_reproducer(
        self,
        target_id: str,
        *,
        reproducer_digest: str,
    ) -> FuzzRegressionBinding:
        key = _text("target_id", target_id)
        try:
            target = self._targets[key]
        except KeyError as exc:
            raise OperationsAssuranceError("unknown fuzz target") from exc
        return FuzzRegressionBinding(
            target.digest,
            _sha("reproducer_digest", reproducer_digest),
            target.regression_test_target,
        )


# ---------------------------------------------------------------------------
# VOL-199: canonical generator library bound to invariant identities
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GeneratorSpec:
    generator_id: str
    invariant_id: str
    state_machine: str
    value_domain: str
    min_seed: int
    max_seed: int

    def __post_init__(self) -> None:
        for name in ("generator_id", "invariant_id", "state_machine", "value_domain"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "min_seed", _integer("min_seed", self.min_seed))
        object.__setattr__(self, "max_seed", _integer("max_seed", self.max_seed))
        if self.max_seed < self.min_seed:
            raise OperationsAssuranceError("generator seed range is inverted")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "generator_id": self.generator_id,
                "invariant_id": self.invariant_id,
                "state_machine": self.state_machine,
                "value_domain": self.value_domain,
                "min_seed": self.min_seed,
                "max_seed": self.max_seed,
            }
        )


@dataclass(frozen=True, slots=True)
class GeneratorBinding:
    generator_digest: str
    invariant_id: str
    seed: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "generator_digest", _sha("generator_digest", self.generator_digest)
        )
        object.__setattr__(self, "invariant_id", _text("invariant_id", self.invariant_id))
        object.__setattr__(self, "seed", _integer("seed", self.seed))


class GeneratorRegistry:
    def __init__(
        self,
        generators: Iterable[GeneratorSpec],
        *,
        invariant_ids: Iterable[str],
    ) -> None:
        invariants = set(_texts("invariant_id", invariant_ids))
        items = tuple(generators)
        if not items:
            raise OperationsAssuranceError("generator registry cannot be empty")
        ids = [item.generator_id for item in items]
        if len(ids) != len(set(ids)):
            raise OperationsAssuranceError("generator identities must be unique")
        for item in items:
            if item.invariant_id not in invariants:
                raise OperationsAssuranceError(
                    "generator references unknown invariant identity"
                )
        self._items = {item.generator_id: item for item in items}

    def bind(self, generator_id: str, *, seed: int) -> GeneratorBinding:
        key = _text("generator_id", generator_id)
        try:
            item = self._items[key]
        except KeyError as exc:
            raise OperationsAssuranceError("unknown generator identity") from exc
        normalized_seed = _integer("seed", seed)
        if not item.min_seed <= normalized_seed <= item.max_seed:
            raise OperationsAssuranceError("generator seed outside declared domain")
        return GeneratorBinding(item.digest, item.invariant_id, normalized_seed)


# ---------------------------------------------------------------------------
# VOL-200: ranked candidate materialization and exact-head proof/test gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FormalCandidateSelection:
    candidate_ids: tuple[str, ...]
    candidate_digests: tuple[str, ...]
    exact_head_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_ids", _texts("candidate_id", self.candidate_ids)
        )
        digests = tuple(_sha("candidate_digest", value) for value in self.candidate_digests)
        if len(digests) != len(self.candidate_ids):
            raise OperationsAssuranceError(
                "candidate identity/digest cardinality mismatch"
            )
        if len(set(digests)) != len(digests):
            raise OperationsAssuranceError("candidate digests must be unique")
        object.__setattr__(self, "candidate_digests", digests)
        object.__setattr__(
            self, "exact_head_sha", _sha("exact_head_sha", self.exact_head_sha, length=40)
        )

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "candidate_ids": list(self.candidate_ids),
                "candidate_digests": list(self.candidate_digests),
                "exact_head_sha": self.exact_head_sha,
            }
        )


@dataclass(frozen=True, slots=True)
class FormalConformanceDecision:
    selection_digest: str
    handoff_digest: str
    test_targets: tuple[str, ...]
    blockers: tuple[str, ...]
    conformant: bool
    completion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "selection_digest", _sha("selection_digest", self.selection_digest)
        )
        object.__setattr__(self, "handoff_digest", _sha("handoff_digest", self.handoff_digest))
        object.__setattr__(self, "test_targets", _texts("test_target", self.test_targets))
        object.__setattr__(
            self, "blockers", _texts("blocker", self.blockers, allow_empty=True)
        )
        if not isinstance(self.conformant, bool):
            raise OperationsAssuranceError("conformant must be boolean")
        if self.conformant != (not self.blockers):
            raise OperationsAssuranceError(
                "formal conformance state must match blockers"
            )
        if self.completion_authority is not False:
            raise OperationsAssuranceError(
                "formal conformance evidence cannot self-grant completion authority"
            )


def assess_formal_conformance(
    selection: FormalCandidateSelection,
    *,
    handoff_digest: str,
    test_targets: Iterable[str],
    exact_head_sha: str,
    test_results: Mapping[str, str],
) -> FormalConformanceDecision:
    reported_head = _sha("exact_head_sha", exact_head_sha, length=40)
    if reported_head != selection.exact_head_sha:
        raise OperationsAssuranceError(
            "formal conformance result is not bound to selected exact head"
        )
    targets = _texts("test_target", test_targets)
    if set(test_results) != set(targets):
        raise OperationsAssuranceError(
            "formal conformance results must cover exact test inventory"
        )
    blockers = tuple(
        sorted(
            f"{target}:{test_results[target]}"
            for target in targets
            if test_results[target] != "success"
        )
    )
    return FormalConformanceDecision(
        selection.digest,
        _sha("handoff_digest", handoff_digest),
        targets,
        blockers,
        not blockers,
    )


__all__ = [
    "CanaryPromotionDecision",
    "CanaryPromotionPolicy",
    "CanaryQualityVector",
    "ChangeClassification",
    "ContractTemplate",
    "ContractTemplateRegistry",
    "FaultDefinition",
    "FaultLibrary",
    "FaultPlan",
    "FeatureFlagSetPolicy",
    "FlagCombinationConstraint",
    "FlagDescriptor",
    "FlagSetDecision",
    "FormalCandidateSelection",
    "FormalConformanceDecision",
    "FuzzRegressionBinding",
    "FuzzTarget",
    "FuzzTargetRegistry",
    "GeneratedTemplateReceipt",
    "GeneratorBinding",
    "GeneratorRegistry",
    "GeneratorSpec",
    "MergeReadinessBinding",
    "MergeReadinessDecision",
    "OperationsAssuranceError",
    "RecoveryDrillPlan",
    "RecoveryDrillScheduler",
    "RecoveryFinding",
    "RollbackProof",
    "RollbackQualification",
    "SimulationAdapterProfile",
    "SimulationSwitchReceipt",
    "assess_formal_conformance",
    "qualify_rollback",
    "select_simulation_adapter",
]
