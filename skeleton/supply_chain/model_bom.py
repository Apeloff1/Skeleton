"""Privacy-preserving immutable model bill of materials for VOL-179."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KINDS = frozenset({"base_model", "adapter", "tokenizer", "runtime"})
_MAX_COMPONENTS = 10_000


class MBOMError(ValueError):
    """Model BOM state is malformed, ambiguous, or unsafe."""


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MBOMError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MBOMError(f"{field} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class ModelComponent:
    component_id: str
    kind: str
    artifact_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _id(self.component_id, "component_id"))
        if not isinstance(self.kind, str) or self.kind not in _KINDS:
            raise MBOMError("invalid model component kind")
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )


@dataclass(frozen=True, slots=True)
class ModelLineage:
    training_run_id: str
    training_evidence_digest: str
    dataset_ref_digest: str
    post_training_run_id: str | None = None
    post_training_evidence_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "training_run_id",
            _id(self.training_run_id, "training_run_id"),
        )
        object.__setattr__(
            self,
            "training_evidence_digest",
            _sha(self.training_evidence_digest, "training_evidence_digest"),
        )
        object.__setattr__(
            self,
            "dataset_ref_digest",
            _sha(self.dataset_ref_digest, "dataset_ref_digest"),
        )
        if (self.post_training_run_id is None) != (
            self.post_training_evidence_digest is None
        ):
            raise MBOMError("post training lineage incomplete")
        if self.post_training_run_id is not None:
            object.__setattr__(
                self,
                "post_training_run_id",
                _id(self.post_training_run_id, "post_training_run_id"),
            )
            object.__setattr__(
                self,
                "post_training_evidence_digest",
                _sha(
                    self.post_training_evidence_digest,
                    "post_training_evidence_digest",
                ),
            )


@dataclass(frozen=True, slots=True)
class MBOM:
    model_id: str
    model_artifact_digest: str
    components: tuple[ModelComponent, ...]
    lineage: ModelLineage

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _id(self.model_id, "model_id"))
        object.__setattr__(
            self,
            "model_artifact_digest",
            _sha(self.model_artifact_digest, "model_artifact_digest"),
        )
        if not isinstance(self.components, tuple) or not self.components:
            raise MBOMError("components must be non-empty tuple")
        if len(self.components) > _MAX_COMPONENTS:
            raise MBOMError("component count exceeds safety bound")
        if any(not isinstance(item, ModelComponent) for item in self.components):
            raise MBOMError("components must contain ModelComponent")
        if not isinstance(self.lineage, ModelLineage):
            raise MBOMError("lineage must be ModelLineage")
        ids = [item.component_id for item in self.components]
        if len(ids) != len(set(ids)):
            raise MBOMError("duplicate component")
        canonical = tuple(sorted(self.components, key=lambda item: item.component_id))
        if self.components != canonical:
            raise MBOMError("components must be canonical order")

    @property
    def digest(self) -> str:
        body = {
            "model_id": self.model_id,
            "model": self.model_artifact_digest,
            "components": [
                (item.component_id, item.kind, item.artifact_digest)
                for item in self.components
            ],
            "lineage": (
                self.lineage.training_run_id,
                self.lineage.training_evidence_digest,
                self.lineage.dataset_ref_digest,
                self.lineage.post_training_run_id,
                self.lineage.post_training_evidence_digest,
            ),
        }
        return hashlib.sha256(
            json.dumps(
                body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest()


__all__ = [
    "MBOM",
    "MBOMError",
    "ModelComponent",
    "ModelLineage",
]
