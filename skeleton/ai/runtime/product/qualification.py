"""Evidence bridge from trained candidate to lifecycle validation.

This module does not evaluate a model, query a holdout, run Mirror Room, or
activate production.  It binds the exact identities emitted by those existing
authorities into one deterministic lifecycle evidence bundle.

The bridge intentionally accepts objects structurally so it can consume the
canonical MirrorPromotionEvidence and PromotionEvidence classes when their PRs
land without copying or importing their implementations into this branch.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping


class LearningQualificationError(RuntimeError):
    """Cross-plane learning qualification evidence cannot be reconciled."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LearningQualificationError(
            "qualification evidence is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningQualificationError(
            f"{name} must be non-empty text"
        )
    result = value.strip()
    if len(result) > maximum:
        raise LearningQualificationError(
            f"{name} exceeds {maximum} characters"
        )
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise LearningQualificationError(
            f"{name} must be lowercase sha256"
        )
    return result


def _attribute(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except AttributeError as exc:
        raise LearningQualificationError(
            f"qualification evidence lacks {name}"
        ) from exc


@dataclass(frozen=True, slots=True)
class MirrorModelBinding:
    """Explicit mapping from model artifacts into Mirror/firewall identities."""

    candidate_model_digest: str
    baseline_model_digest: str
    candidate_artifact_sha256: str
    training_plan_digest: str
    mirror_candidate_id: str
    mirror_candidate_digest: str
    mirror_baseline_candidate_id: str
    mirror_baseline_candidate_digest: str
    firewall_candidate_id: str
    camera_coverage_digest: str | None = None
    method_allocation_digest: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "candidate_model_digest",
            "baseline_model_digest",
            "candidate_artifact_sha256",
            "training_plan_digest",
            "mirror_candidate_digest",
            "mirror_baseline_candidate_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha(getattr(self, name), name),
            )
        for name in (
            "mirror_candidate_id",
            "mirror_baseline_candidate_id",
            "firewall_candidate_id",
        ):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name),
            )
        if self.candidate_model_digest == self.baseline_model_digest:
            raise LearningQualificationError(
                "candidate and baseline model digests must differ"
            )
        for name in (
            "camera_coverage_digest",
            "method_allocation_digest",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _sha(value, name))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_model_digest": self.candidate_model_digest,
                "baseline_model_digest": self.baseline_model_digest,
                "candidate_artifact_sha256": self.candidate_artifact_sha256,
                "training_plan_digest": self.training_plan_digest,
                "mirror_candidate_id": self.mirror_candidate_id,
                "mirror_candidate_digest": self.mirror_candidate_digest,
                "mirror_baseline_candidate_id": (
                    self.mirror_baseline_candidate_id
                ),
                "mirror_baseline_candidate_digest": (
                    self.mirror_baseline_candidate_digest
                ),
                "firewall_candidate_id": self.firewall_candidate_id,
                "camera_coverage_digest": self.camera_coverage_digest,
                "method_allocation_digest": self.method_allocation_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class LearningQualificationBundle:
    """Non-authoritative evidence suitable for lifecycle validation."""

    binding_digest: str
    candidate_model_digest: str
    baseline_model_digest: str
    candidate_artifact_sha256: str
    training_plan_digest: str
    mirror_evidence_digest: str
    firewall_evidence_digest: str
    mirror_verifier_id: str
    firewall_evaluator_identity: str
    lifecycle_evidence_refs: tuple[str, ...]
    camera_coverage_digest: str | None
    method_allocation_digest: str | None
    production_authority: bool
    direct_self_modify: bool
    qualification_digest: str

    def __post_init__(self) -> None:
        if self.production_authority is not False:
            raise LearningQualificationError(
                "qualification cannot grant production authority"
            )
        if self.direct_self_modify is not False:
            raise LearningQualificationError(
                "qualification cannot self-modify production"
            )

    def lifecycle_validation_kwargs(
        self,
        *,
        verifier_id: str | None = None,
    ) -> dict[str, object]:
        """Arguments for ModelLifecycleRegistry.transition(... VALIDATED ...).

        The caller still chooses and invokes the lifecycle authority.  This
        adapter only supplies the exact candidate digest, an independent
        verifier identity, and the already-bound evidence references.
        """

        verifier = (
            self.mirror_verifier_id
            if verifier_id is None
            else _text(verifier_id, "lifecycle verifier_id")
        )
        if verifier == self.firewall_evaluator_identity:
            # Distinct identities are preferable so one evaluator does not
            # silently become the sole cross-plane authority.
            raise LearningQualificationError(
                "lifecycle verifier must differ from firewall evaluator identity"
            )
        return {
            "model_digest": self.candidate_model_digest,
            "verifier_id": verifier,
            "evidence_refs": self.lifecycle_evidence_refs,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_qualification.v1",
            "binding_digest": self.binding_digest,
            "candidate_model_digest": self.candidate_model_digest,
            "baseline_model_digest": self.baseline_model_digest,
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "training_plan_digest": self.training_plan_digest,
            "mirror_evidence_digest": self.mirror_evidence_digest,
            "firewall_evidence_digest": self.firewall_evidence_digest,
            "mirror_verifier_id": self.mirror_verifier_id,
            "firewall_evaluator_identity": self.firewall_evaluator_identity,
            "lifecycle_evidence_refs": list(self.lifecycle_evidence_refs),
            "camera_coverage_digest": self.camera_coverage_digest,
            "method_allocation_digest": self.method_allocation_digest,
            "production_authority": False,
            "direct_self_modify": False,
            "qualification_digest": self.qualification_digest,
        }


def qualify_learning_candidate(
    *,
    training_receipt: Mapping[str, object],
    binding: MirrorModelBinding,
    mirror_promotion_evidence: object,
    firewall_promotion_evidence: object,
) -> LearningQualificationBundle:
    """Reconcile exact training, Mirror Room and firewall evidence identities."""

    if not isinstance(training_receipt, Mapping):
        raise TypeError("training_receipt must be a mapping")
    if not isinstance(binding, MirrorModelBinding):
        raise TypeError("binding must be MirrorModelBinding")

    model_digest = _sha(
        training_receipt.get("model_digest"),
        "training receipt model_digest",
    )
    artifact_sha = _sha(
        training_receipt.get("artifact_sha256"),
        "training receipt artifact_sha256",
    )
    plan = training_receipt.get("training_plan")
    if not isinstance(plan, Mapping):
        raise LearningQualificationError(
            "training receipt lacks training_plan"
        )
    plan_digest = _sha(
        plan.get("plan_digest"),
        "training plan digest",
    )
    if model_digest != binding.candidate_model_digest:
        raise LearningQualificationError(
            "training receipt candidate model identity drift"
        )
    if artifact_sha != binding.candidate_artifact_sha256:
        raise LearningQualificationError(
            "training receipt artifact identity drift"
        )
    if plan_digest != binding.training_plan_digest:
        raise LearningQualificationError(
            "training receipt plan identity drift"
        )

    mirror_candidate_id = _text(
        _attribute(mirror_promotion_evidence, "candidate_id"),
        "mirror candidate_id",
    )
    mirror_candidate_digest = _sha(
        _attribute(mirror_promotion_evidence, "candidate_digest"),
        "mirror candidate_digest",
    )
    mirror_baseline_id = _text(
        _attribute(mirror_promotion_evidence, "baseline_candidate_id"),
        "mirror baseline_candidate_id",
    )
    mirror_baseline_digest = _sha(
        _attribute(
            mirror_promotion_evidence,
            "baseline_candidate_digest",
        ),
        "mirror baseline_candidate_digest",
    )
    mirror_digest = _sha(
        _attribute(mirror_promotion_evidence, "digest"),
        "mirror evidence digest",
    )
    mirror_verifier = _text(
        _attribute(mirror_promotion_evidence, "verifier_id"),
        "mirror verifier_id",
    )
    if bool(
        _attribute(
            mirror_promotion_evidence,
            "production_authority",
        )
    ):
        raise LearningQualificationError(
            "Mirror evidence unexpectedly grants production authority"
        )
    if bool(
        _attribute(mirror_promotion_evidence, "direct_self_modify")
    ):
        raise LearningQualificationError(
            "Mirror evidence unexpectedly grants self-modification"
        )

    if (
        mirror_candidate_id != binding.mirror_candidate_id
        or mirror_candidate_digest != binding.mirror_candidate_digest
        or mirror_baseline_id != binding.mirror_baseline_candidate_id
        or mirror_baseline_digest
        != binding.mirror_baseline_candidate_digest
    ):
        raise LearningQualificationError(
            "Mirror Room candidate/baseline binding drift"
        )

    firewall_candidate = _text(
        _attribute(firewall_promotion_evidence, "candidate_id"),
        "firewall candidate_id",
    )
    firewall_digest = _sha(
        _attribute(firewall_promotion_evidence, "digest"),
        "firewall evidence digest",
    )
    firewall_evaluator = _text(
        _attribute(
            firewall_promotion_evidence,
            "evaluator_identity",
        ),
        "firewall evaluator_identity",
    )
    holdout_used = _attribute(
        firewall_promotion_evidence,
        "holdout_queries_used",
    )
    holdout_budget = _attribute(
        firewall_promotion_evidence,
        "holdout_query_budget",
    )
    if (
        isinstance(holdout_used, bool)
        or not isinstance(holdout_used, int)
        or isinstance(holdout_budget, bool)
        or not isinstance(holdout_budget, int)
        or holdout_used < 1
        or holdout_used > holdout_budget
    ):
        raise LearningQualificationError(
            "firewall promotion query budget evidence is invalid"
        )
    if firewall_candidate != binding.firewall_candidate_id:
        raise LearningQualificationError(
            "evaluation firewall candidate identity drift"
        )

    refs = [
        "learning-binding-sha256:" + binding.digest,
        "training-plan-sha256:" + binding.training_plan_digest,
        "mirror-room-evidence-sha256:" + mirror_digest,
        "evaluation-firewall-evidence-sha256:" + firewall_digest,
    ]
    if binding.camera_coverage_digest is not None:
        refs.append(
            "camera-coverage-sha256:"
            + binding.camera_coverage_digest
        )
    if binding.method_allocation_digest is not None:
        refs.append(
            "method-allocation-sha256:"
            + binding.method_allocation_digest
        )
    payload = {
        "schema_version": "skeleton.learning_qualification.v1",
        "binding_digest": binding.digest,
        "candidate_model_digest": binding.candidate_model_digest,
        "baseline_model_digest": binding.baseline_model_digest,
        "candidate_artifact_sha256": binding.candidate_artifact_sha256,
        "training_plan_digest": binding.training_plan_digest,
        "mirror_evidence_digest": mirror_digest,
        "firewall_evidence_digest": firewall_digest,
        "mirror_verifier_id": mirror_verifier,
        "firewall_evaluator_identity": firewall_evaluator,
        "lifecycle_evidence_refs": refs,
        "camera_coverage_digest": binding.camera_coverage_digest,
        "method_allocation_digest": binding.method_allocation_digest,
        "production_authority": False,
        "direct_self_modify": False,
    }
    return LearningQualificationBundle(
        binding_digest=binding.digest,
        candidate_model_digest=binding.candidate_model_digest,
        baseline_model_digest=binding.baseline_model_digest,
        candidate_artifact_sha256=binding.candidate_artifact_sha256,
        training_plan_digest=binding.training_plan_digest,
        mirror_evidence_digest=mirror_digest,
        firewall_evidence_digest=firewall_digest,
        mirror_verifier_id=mirror_verifier,
        firewall_evaluator_identity=firewall_evaluator,
        lifecycle_evidence_refs=tuple(refs),
        camera_coverage_digest=binding.camera_coverage_digest,
        method_allocation_digest=binding.method_allocation_digest,
        production_authority=False,
        direct_self_modify=False,
        qualification_digest=_digest(payload),
    )


__all__ = [
    "LearningQualificationBundle",
    "LearningQualificationError",
    "MirrorModelBinding",
    "qualify_learning_candidate",
]
