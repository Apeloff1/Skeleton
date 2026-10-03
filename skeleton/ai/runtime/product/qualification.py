"""Bind training, Mirror Room, and promotion holdout evidence.

Qualification is deliberately non-executing. It proves that independently
produced evidence refers to one exact local-model candidate and baseline, then
emits digest-bound lifecycle evidence. It cannot activate a model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from skeleton.eval.firewall import PromotionEvidence
from skeleton.learning.mirror_room import MirrorPromotionEvidence


class LearningQualificationError(RuntimeError):
    """Learning evidence cannot qualify one exact candidate."""


def _stable_json(value: object) -> str:
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
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningQualificationError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise LearningQualificationError(
            f"{name} must be normalized and bounded"
        )
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise LearningQualificationError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class MirrorModelBinding:
    """Explicit mapping between model identity and sandbox/evaluation identity."""

    candidate_model_digest: str
    baseline_model_digest: str
    candidate_artifact_sha256: str
    mirror_candidate_id: str
    mirror_candidate_digest: str
    mirror_baseline_candidate_id: str
    mirror_baseline_candidate_digest: str
    firewall_candidate_id: str

    def __post_init__(self) -> None:
        for name in (
            "candidate_model_digest",
            "baseline_model_digest",
            "candidate_artifact_sha256",
            "mirror_candidate_digest",
            "mirror_baseline_candidate_digest",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
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
        expected = "local-model:" + self.candidate_model_digest
        if self.firewall_candidate_id != expected:
            raise LearningQualificationError(
                "firewall candidate identity must bind candidate model digest"
            )

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, str]:
        return {
            "candidate_model_digest": self.candidate_model_digest,
            "baseline_model_digest": self.baseline_model_digest,
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "mirror_candidate_id": self.mirror_candidate_id,
            "mirror_candidate_digest": self.mirror_candidate_digest,
            "mirror_baseline_candidate_id": self.mirror_baseline_candidate_id,
            "mirror_baseline_candidate_digest": (
                self.mirror_baseline_candidate_digest
            ),
            "firewall_candidate_id": self.firewall_candidate_id,
        }


@dataclass(frozen=True, slots=True)
class LearningQualificationBundle:
    binding_digest: str
    candidate_model_digest: str
    baseline_model_digest: str
    candidate_artifact_sha256: str
    native_training_receipt_digest: str
    mirror_evidence_digest: str
    firewall_evidence_digest: str
    mirror_verifier_id: str
    firewall_evaluator_identity: str
    lifecycle_evidence_refs: tuple[str, ...]
    production_authority: bool = False
    direct_self_modify: bool = False
    qualification_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "binding_digest",
            "candidate_model_digest",
            "baseline_model_digest",
            "candidate_artifact_sha256",
            "native_training_receipt_digest",
            "mirror_evidence_digest",
            "firewall_evidence_digest",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        object.__setattr__(
            self,
            "mirror_verifier_id",
            _text(self.mirror_verifier_id, "mirror_verifier_id"),
        )
        object.__setattr__(
            self,
            "firewall_evaluator_identity",
            _text(
                self.firewall_evaluator_identity,
                "firewall_evaluator_identity",
            ),
        )
        refs = tuple(
            _text(item, "lifecycle_evidence_ref")
            for item in self.lifecycle_evidence_refs
        )
        if len(refs) < 5 or len(refs) != len(set(refs)):
            raise LearningQualificationError(
                "qualification requires unique cross-authority evidence"
            )
        object.__setattr__(self, "lifecycle_evidence_refs", refs)
        if self.production_authority is not False:
            raise LearningQualificationError(
                "qualification cannot grant production authority"
            )
        if self.direct_self_modify is not False:
            raise LearningQualificationError(
                "qualification cannot grant direct self-modification"
            )
        expected = _digest(self._payload())
        if self.qualification_digest:
            claimed = _sha(
                self.qualification_digest,
                "qualification_digest",
            )
            if claimed != expected:
                raise LearningQualificationError(
                    "qualification digest does not match evidence"
                )
        object.__setattr__(self, "qualification_digest", expected)

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_qualification.v1",
            "binding_digest": self.binding_digest,
            "candidate_model_digest": self.candidate_model_digest,
            "baseline_model_digest": self.baseline_model_digest,
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "native_training_receipt_digest": (
                self.native_training_receipt_digest
            ),
            "mirror_evidence_digest": self.mirror_evidence_digest,
            "firewall_evidence_digest": self.firewall_evidence_digest,
            "mirror_verifier_id": self.mirror_verifier_id,
            "firewall_evaluator_identity": (
                self.firewall_evaluator_identity
            ),
            "lifecycle_evidence_refs": list(self.lifecycle_evidence_refs),
            "production_authority": False,
            "direct_self_modify": False,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self._payload(),
            "qualification_digest": self.qualification_digest,
        }


def qualify_learning_candidate(
    *,
    training_receipt: Mapping[str, object],
    binding: MirrorModelBinding,
    mirror_promotion_evidence: MirrorPromotionEvidence,
    firewall_promotion_evidence: PromotionEvidence,
) -> LearningQualificationBundle:
    """Qualify one exact candidate without granting deployment authority."""

    if not isinstance(training_receipt, Mapping):
        raise TypeError("training_receipt must be a mapping")
    if not isinstance(binding, MirrorModelBinding):
        raise TypeError("binding must be MirrorModelBinding")
    if not isinstance(
        mirror_promotion_evidence,
        MirrorPromotionEvidence,
    ):
        raise TypeError(
            "mirror_promotion_evidence must be MirrorPromotionEvidence"
        )
    if not isinstance(firewall_promotion_evidence, PromotionEvidence):
        raise TypeError(
            "firewall_promotion_evidence must be PromotionEvidence"
        )

    candidate_model = _sha(
        training_receipt.get("model_digest"),
        "training model_digest",
    )
    candidate_artifact = _sha(
        training_receipt.get("artifact_sha256"),
        "training artifact_sha256",
    )
    native_receipt = _sha(
        training_receipt.get("training_receipt_digest"),
        "training_receipt_digest",
    )
    if candidate_model != binding.candidate_model_digest:
        raise LearningQualificationError(
            "training receipt model differs from candidate binding"
        )
    if candidate_artifact != binding.candidate_artifact_sha256:
        raise LearningQualificationError(
            "training receipt artifact differs from candidate binding"
        )
    if training_receipt.get("credential_free") is not True:
        raise LearningQualificationError(
            "reverse qualification requires credential-free local training"
        )

    mirror = mirror_promotion_evidence
    if (
        mirror.candidate_id != binding.mirror_candidate_id
        or mirror.candidate_digest != binding.mirror_candidate_digest
        or mirror.baseline_candidate_id
        != binding.mirror_baseline_candidate_id
        or mirror.baseline_candidate_digest
        != binding.mirror_baseline_candidate_digest
    ):
        raise LearningQualificationError(
            "Mirror Room evidence differs from explicit model binding"
        )
    if (
        mirror.production_authority is not False
        or mirror.direct_self_modify is not False
    ):
        raise LearningQualificationError(
            "Mirror Room evidence carries forbidden authority"
        )

    firewall = firewall_promotion_evidence
    if firewall.candidate_id != binding.firewall_candidate_id:
        raise LearningQualificationError(
            "firewall evidence differs from candidate binding"
        )
    if (
        firewall.production_authority is not False
        or firewall.direct_self_modify is not False
    ):
        raise LearningQualificationError(
            "firewall evidence carries forbidden authority"
        )

    mirror_digest = _sha(mirror.digest, "mirror_evidence_digest")
    firewall_digest = _sha(firewall.digest, "firewall_evidence_digest")
    refs = (
        "training-receipt-sha256:" + native_receipt,
        "candidate-artifact-sha256:" + candidate_artifact,
        "baseline-model-sha256:" + binding.baseline_model_digest,
        "mirror-room-evidence-sha256:" + mirror_digest,
        "evaluation-firewall-evidence-sha256:" + firewall_digest,
        "model-binding-sha256:" + binding.digest,
    )
    return LearningQualificationBundle(
        binding_digest=binding.digest,
        candidate_model_digest=candidate_model,
        baseline_model_digest=binding.baseline_model_digest,
        candidate_artifact_sha256=candidate_artifact,
        native_training_receipt_digest=native_receipt,
        mirror_evidence_digest=mirror_digest,
        firewall_evidence_digest=firewall_digest,
        mirror_verifier_id=mirror.verifier_id,
        firewall_evaluator_identity=firewall.evaluator_identity,
        lifecycle_evidence_refs=refs,
    )


__all__ = [
    "LearningQualificationBundle",
    "LearningQualificationError",
    "MirrorModelBinding",
    "qualify_learning_candidate",
]
