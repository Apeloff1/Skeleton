"""Promotion handoff for Mirror Room.

This module produces auditable *evidence* for the existing promotion/release
planes.  It intentionally has no method that mutates production behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.contracts.canonical import EvidenceRef

from .contracts import MirrorRoomError, _digest, _non_negative_int, _token, _tokens
from .engine import MirrorRunReceipt


@dataclass(frozen=True, slots=True)
class MirrorPromotionEvidence:
    experiment_id: str
    run_id: str
    run_digest: str
    manifest_digest: str
    baseline_candidate_id: str
    baseline_candidate_digest: str
    candidate_id: str
    candidate_digest: str
    candidate_version: str
    holdout_report_digest: str
    validation_report_digests: tuple[str, ...]
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    verified_at: int
    rollback_candidate_id: str
    rollback_candidate_digest: str
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiment_id", _token("experiment_id", self.experiment_id))
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise MirrorRoomError("run_id must be non-empty")
        for field in (
            "run_digest",
            "manifest_digest",
            "baseline_candidate_digest",
            "candidate_digest",
            "holdout_report_digest",
            "rollback_candidate_digest",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or len(value) != 64:
                raise MirrorRoomError(f"{field} must be sha256")
        object.__setattr__(
            self,
            "validation_report_digests",
            tuple(self.validation_report_digests),
        )
        if not self.validation_report_digests or any(
            not isinstance(value, str) or len(value) != 64
            for value in self.validation_report_digests
        ):
            raise MirrorRoomError("validation report digests must be non-empty sha256 values")
        object.__setattr__(self, "verifier_id", _token("verifier_id", self.verifier_id))
        refs = _tokens("evaluation_ref", self.evaluation_refs, allow_empty=False)
        if len(refs) < 2:
            raise MirrorRoomError("promotion handoff requires at least two evaluation references")
        object.__setattr__(self, "evaluation_refs", refs)
        object.__setattr__(
            self,
            "verified_at",
            _non_negative_int("verified_at", self.verified_at),
        )
        for field in (
            "baseline_candidate_id",
            "candidate_id",
            "candidate_version",
            "rollback_candidate_id",
        ):
            object.__setattr__(self, field, _token(field, getattr(self, field)))
        if self.production_authority is not False:
            raise MirrorRoomError("Mirror promotion evidence cannot grant production authority")
        if self.direct_self_modify is not False:
            raise MirrorRoomError("Mirror promotion evidence cannot self-modify production")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "experiment_id": self.experiment_id,
                "run_id": self.run_id,
                "run_digest": self.run_digest,
                "manifest_digest": self.manifest_digest,
                "baseline_candidate_id": self.baseline_candidate_id,
                "baseline_candidate_digest": self.baseline_candidate_digest,
                "candidate_id": self.candidate_id,
                "candidate_digest": self.candidate_digest,
                "candidate_version": self.candidate_version,
                "holdout_report_digest": self.holdout_report_digest,
                "validation_report_digests": list(self.validation_report_digests),
                "verifier_id": self.verifier_id,
                "evaluation_refs": list(self.evaluation_refs),
                "verified_at": self.verified_at,
                "rollback_candidate_id": self.rollback_candidate_id,
                "rollback_candidate_digest": self.rollback_candidate_digest,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )

    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=f"mirror-room:{self.experiment_id}:{self.run_id}",
            digest=self.digest,
            category="mirror_room_promotion_evidence",
        )


def qualify_for_external_promotion(
    run: MirrorRunReceipt,
    *,
    verifier_id: str,
    evaluation_refs: tuple[str, ...],
    verified_at: int,
) -> MirrorPromotionEvidence:
    """Create a non-authoritative promotion handoff after sealed holdout."""

    if not isinstance(run, MirrorRunReceipt):
        raise TypeError("run must be MirrorRunReceipt")
    verifier = _token("verifier_id", verifier_id)
    if not run.eligible_for_external_promotion or run.holdout_report is None:
        raise MirrorRoomError("Mirror run did not qualify on sealed holdout")
    candidate = run.final_sandbox_champion
    if verifier == candidate.producer_id:
        raise MirrorRoomError("candidate producer cannot independently verify promotion")
    if verifier == run.executor_id:
        raise MirrorRoomError("sandbox evaluator cannot independently verify promotion")

    validation_digests = []
    selected_ids = set()
    for generation in run.generations:
        for evaluation in generation.evaluations:
            if evaluation.selected:
                validation_digests.append(evaluation.validation_report.digest)
                selected_ids.add(evaluation.candidate.candidate_id)
    if candidate.candidate_id not in selected_ids:
        raise MirrorRoomError("final candidate lacks selected validation lineage")
    if not validation_digests:
        raise MirrorRoomError("promotion handoff requires validation lineage")

    baseline = run.production_baseline
    return MirrorPromotionEvidence(
        experiment_id=run.experiment_id,
        run_id=run.run_id,
        run_digest=run.digest,
        manifest_digest=run.manifest_digest,
        baseline_candidate_id=baseline.candidate_id,
        baseline_candidate_digest=baseline.digest,
        candidate_id=candidate.candidate_id,
        candidate_digest=candidate.digest,
        candidate_version=candidate.version,
        holdout_report_digest=run.holdout_report.digest,
        validation_report_digests=tuple(validation_digests),
        verifier_id=verifier,
        evaluation_refs=evaluation_refs,
        verified_at=verified_at,
        rollback_candidate_id=baseline.candidate_id,
        rollback_candidate_digest=baseline.digest,
    )


__all__ = [
    "MirrorPromotionEvidence",
    "qualify_for_external_promotion",
]
