"""Fail-closed training-data integrity admission.

This control plane turns poisoning/backdoor concerns into executable admission
rules.  It does not attempt to prove a corpus is benign; it requires immutable
transform identity, source dispositions, anomaly evidence and trigger-canary
coverage before a dataset can be admitted to a training run.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping, Sequence


class TrainingIntegrityError(RuntimeError):
    """Training data cannot be admitted with the supplied integrity evidence."""


SOURCE_DISPOSITIONS = {"admit", "quarantine", "reject"}
REQUIRED_SIGNAL_KINDS = {
    "content-anomaly",
    "label-anomaly",
    "source-ablation",
    "trigger-canary",
}


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
        raise TrainingIntegrityError("integrity value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingIntegrityError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise TrainingIntegrityError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise TrainingIntegrityError(f"{name} must be lowercase sha256")
    return result


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        _json(value)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TrainingIntegrityError("metadata contains non-finite number")
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TrainingIntegrityError("metadata object keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TrainingIntegrityError("metadata contains non-JSON value")


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class TransformIdentity:
    transform_id: str
    implementation_digest: str
    configuration_digest: str
    signer_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "transform_id", _text("transform_id", self.transform_id))
        object.__setattr__(
            self,
            "implementation_digest",
            _sha("implementation_digest", self.implementation_digest),
        )
        object.__setattr__(
            self,
            "configuration_digest",
            _sha("configuration_digest", self.configuration_digest),
        )
        object.__setattr__(self, "signer_ref", _text("signer_ref", self.signer_ref))

    def as_dict(self) -> dict[str, object]:
        return {
            "transform_id": self.transform_id,
            "implementation_digest": self.implementation_digest,
            "configuration_digest": self.configuration_digest,
            "signer_ref": self.signer_ref,
        }

    @property
    def identity(self) -> str:
        return "transform:" + _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class IntegritySignal:
    source_id: str
    kind: str
    detector_id: str
    detector_digest: str
    passed: bool
    evidence_ref: str
    score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if self.kind not in REQUIRED_SIGNAL_KINDS:
            raise TrainingIntegrityError("unsupported integrity signal kind")
        object.__setattr__(self, "detector_id", _text("detector_id", self.detector_id))
        object.__setattr__(
            self, "detector_digest", _sha("detector_digest", self.detector_digest)
        )
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
                raise TrainingIntegrityError("score must be numeric")
            score = float(self.score)
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise TrainingIntegrityError("score must be finite and in [0, 1]")
            object.__setattr__(self, "score", score)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "source_id": self.source_id,
                "kind": self.kind,
                "detector_id": self.detector_id,
                "detector_digest": self.detector_digest,
                "passed": self.passed,
                "evidence_ref": self.evidence_ref,
                "score": self.score,
            }
        )


@dataclass(frozen=True, slots=True)
class SourceIntegrityDecision:
    source_id: str
    source_digest: str
    disposition: str
    signal_digests: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "source_digest", _sha("source_digest", self.source_digest))
        if self.disposition not in SOURCE_DISPOSITIONS:
            raise TrainingIntegrityError("invalid source disposition")
        values = tuple(_sha("signal_digest", item) for item in self.signal_digests)
        if len(values) != len(set(values)):
            raise TrainingIntegrityError("signal digests must be unique")
        object.__setattr__(self, "signal_digests", tuple(sorted(values)))
        object.__setattr__(self, "rationale", _text("rationale", self.rationale))

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "disposition": self.disposition,
            "signal_digests": list(self.signal_digests),
            "rationale": self.rationale,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class TrainingIntegrityReceipt:
    dataset_id: str
    dataset_digest: str
    transform_identities: tuple[str, ...]
    source_decisions: tuple[SourceIntegrityDecision, ...]
    signal_digests: tuple[str, ...]
    admitted: bool
    policy_digest: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        object.__setattr__(self, "dataset_digest", _sha("dataset_digest", self.dataset_digest))
        object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if not self.transform_identities:
            raise TrainingIntegrityError("at least one signed transform identity is required")
        transforms = tuple(
            sorted(_text("transform identity", item) for item in self.transform_identities)
        )
        if len(transforms) != len(set(transforms)):
            raise TrainingIntegrityError("transform identities must be unique")
        object.__setattr__(self, "transform_identities", transforms)

        decisions = tuple(self.source_decisions)
        if not decisions:
            raise TrainingIntegrityError("source decisions must not be empty")
        if any(not isinstance(item, SourceIntegrityDecision) for item in decisions):
            raise TypeError("source_decisions must contain SourceIntegrityDecision values")
        decisions = tuple(sorted(decisions, key=lambda item: item.source_id))
        ids = [item.source_id for item in decisions]
        if len(ids) != len(set(ids)):
            raise TrainingIntegrityError("source decisions must be unique")
        object.__setattr__(self, "source_decisions", decisions)

        signals = tuple(sorted(_sha("signal_digest", item) for item in self.signal_digests))
        if len(signals) != len(set(signals)):
            raise TrainingIntegrityError("signal digests must be unique")
        decision_signals = tuple(
            sorted(
                digest
                for decision in decisions
                for digest in decision.signal_digests
            )
        )
        if signals != decision_signals:
            raise TrainingIntegrityError(
                "receipt signal inventory must exactly match source decisions"
            )
        object.__setattr__(self, "signal_digests", signals)

        if not isinstance(self.admitted, bool):
            raise TypeError("admitted must be boolean")
        expected_admitted = all(item.disposition == "admit" for item in decisions)
        if self.admitted is not expected_admitted:
            raise TrainingIntegrityError(
                "receipt admission flag disagrees with source dispositions"
            )

        raw_metadata = dict(self.metadata)
        _json(raw_metadata)
        object.__setattr__(self, "metadata", _freeze_json(raw_metadata))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_integrity_receipt.v1",
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "transform_identities": list(self.transform_identities),
            "source_decisions": [item.as_dict() for item in self.source_decisions],
            "signal_digests": list(self.signal_digests),
            "admitted": self.admitted,
            "policy_digest": self.policy_digest,
            "metadata": _thaw_json(self.metadata),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class TrainingIntegrityEvaluationEvidence:
    dataset_id: str
    dataset_digest: str
    source_inventory_digest: str
    transform_inventory_digest: str
    signal_inventory_digest: str
    policy_digest: str
    receipt: TrainingIntegrityReceipt

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        for field_name in (
            "dataset_digest",
            "source_inventory_digest",
            "transform_inventory_digest",
            "signal_inventory_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        if not isinstance(self.receipt, TrainingIntegrityReceipt):
            raise TypeError("receipt must be TrainingIntegrityReceipt")
        if self.receipt.dataset_id != self.dataset_id:
            raise TrainingIntegrityError("evidence dataset id does not match receipt")
        if self.receipt.dataset_digest != self.dataset_digest:
            raise TrainingIntegrityError("evidence dataset digest does not match receipt")
        if self.receipt.policy_digest != self.policy_digest:
            raise TrainingIntegrityError("evidence policy digest does not match receipt")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_integrity_evidence.v1",
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "source_inventory_digest": self.source_inventory_digest,
            "transform_inventory_digest": self.transform_inventory_digest,
            "signal_inventory_digest": self.signal_inventory_digest,
            "policy_digest": self.policy_digest,
            "receipt_digest": self.receipt.digest,
            "admitted": self.receipt.admitted,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class TrainingIntegrityGate:
    def __init__(self, *, policy_digest: str) -> None:
        self.policy_digest = _sha("policy_digest", policy_digest)

    def evaluate(
        self,
        *,
        dataset_id: str,
        dataset_digest: str,
        source_digests: Mapping[str, str],
        transforms: Sequence[TransformIdentity],
        signals: Sequence[IntegritySignal],
    ) -> TrainingIntegrityReceipt:
        if not transforms:
            raise TrainingIntegrityError("training dataset has no signed transform lineage")
        if not source_digests:
            raise TrainingIntegrityError("training dataset has no source inventory")

        normalized_transforms = tuple(transforms)
        if any(not isinstance(item, TransformIdentity) for item in normalized_transforms):
            raise TypeError("transforms must contain TransformIdentity values")
        transform_ids = [item.transform_id for item in normalized_transforms]
        if len(transform_ids) != len(set(transform_ids)):
            raise TrainingIntegrityError("transform ids must be unique")
        transform_identities = tuple(sorted(item.identity for item in normalized_transforms))
        if len(transform_identities) != len(set(transform_identities)):
            raise TrainingIntegrityError("transform identities must be unique")

        source_map: dict[str, str] = {}
        for raw_source_id, raw_digest in source_digests.items():
            source_id = _text("source_id", raw_source_id)
            if source_id in source_map:
                raise TrainingIntegrityError(
                    "source ids collide after normalization"
                )
            source_map[source_id] = _sha("source_digest", raw_digest)

        normalized_signals = tuple(signals)
        by_source: dict[str, list[IntegritySignal]] = {
            source_id: [] for source_id in source_map
        }
        seen_signal_keys: set[tuple[str, str]] = set()
        seen_signal_digests: set[str] = set()
        for signal in normalized_signals:
            if not isinstance(signal, IntegritySignal):
                raise TypeError("signals must contain IntegritySignal values")
            if signal.source_id not in by_source:
                raise TrainingIntegrityError("integrity signal references unknown source")
            key = (signal.source_id, signal.kind)
            if key in seen_signal_keys:
                raise TrainingIntegrityError(
                    "duplicate integrity signal kind for source"
                )
            if signal.digest in seen_signal_digests:
                raise TrainingIntegrityError("duplicate integrity signal evidence")
            seen_signal_keys.add(key)
            seen_signal_digests.add(signal.digest)
            by_source[signal.source_id].append(signal)

        decisions: list[SourceIntegrityDecision] = []
        all_signal_digests: list[str] = []
        for source_id in sorted(source_map):
            rows = by_source[source_id]
            kinds = {row.kind for row in rows}
            missing = REQUIRED_SIGNAL_KINDS - kinds
            if missing:
                disposition = "quarantine"
                rationale = "missing required integrity signals: " + ",".join(sorted(missing))
            elif any(not row.passed for row in rows):
                disposition = "quarantine"
                rationale = "one or more integrity signals failed"
            else:
                disposition = "admit"
                rationale = "required integrity signals passed"
            digests = tuple(sorted(row.digest for row in rows))
            all_signal_digests.extend(digests)
            decisions.append(
                SourceIntegrityDecision(
                    source_id=source_id,
                    source_digest=source_map[source_id],
                    disposition=disposition,
                    signal_digests=digests,
                    rationale=rationale,
                )
            )

        admitted = all(item.disposition == "admit" for item in decisions)
        return TrainingIntegrityReceipt(
            dataset_id=_text("dataset_id", dataset_id),
            dataset_digest=_sha("dataset_digest", dataset_digest),
            transform_identities=transform_identities,
            source_decisions=tuple(decisions),
            signal_digests=tuple(sorted(all_signal_digests)),
            admitted=admitted,
            policy_digest=self.policy_digest,
        )

    def evaluate_evidence(
        self,
        *,
        dataset_id: str,
        dataset_digest: str,
        source_digests: Mapping[str, str],
        transforms: Sequence[TransformIdentity],
        signals: Sequence[IntegritySignal],
    ) -> TrainingIntegrityEvaluationEvidence:
        receipt = self.evaluate(
            dataset_id=dataset_id,
            dataset_digest=dataset_digest,
            source_digests=source_digests,
            transforms=transforms,
            signals=signals,
        )
        normalized_sources: dict[str, str] = {}
        for raw_source_id, raw_digest in source_digests.items():
            source_id = _text("source_id", raw_source_id)
            if source_id in normalized_sources:
                raise TrainingIntegrityError(
                    "source ids collide after normalization"
                )
            normalized_sources[source_id] = _sha("source_digest", raw_digest)
        transform_rows = [
            item.as_dict()
            for item in sorted(
                transforms,
                key=lambda item: item.identity,
            )
        ]
        signal_rows = sorted(
            (
                {
                    "source_id": item.source_id,
                    "kind": item.kind,
                    "detector_id": item.detector_id,
                    "detector_digest": item.detector_digest,
                    "passed": item.passed,
                    "evidence_ref": item.evidence_ref,
                    "score": item.score,
                }
                for item in signals
            ),
            key=lambda item: (
                str(item["source_id"]),
                str(item["kind"]),
                str(item["detector_id"]),
            ),
        )
        return TrainingIntegrityEvaluationEvidence(
            dataset_id=receipt.dataset_id,
            dataset_digest=receipt.dataset_digest,
            source_inventory_digest=_digest(dict(sorted(normalized_sources.items()))),
            transform_inventory_digest=_digest(transform_rows),
            signal_inventory_digest=_digest(signal_rows),
            policy_digest=self.policy_digest,
            receipt=receipt,
        )

    @staticmethod
    def require_admitted(
        receipt: TrainingIntegrityReceipt,
        *,
        expected_policy_digest: str | None = None,
    ) -> None:
        if not isinstance(receipt, TrainingIntegrityReceipt):
            raise TypeError("receipt must be TrainingIntegrityReceipt")
        if expected_policy_digest is not None:
            expected = _sha("expected_policy_digest", expected_policy_digest)
            if receipt.policy_digest != expected:
                raise TrainingIntegrityError(
                    "training integrity receipt policy mismatch"
                )
        if not receipt.admitted:
            raise TrainingIntegrityError("dataset is quarantined and cannot enter training")


__all__ = [
    "IntegritySignal",
    "REQUIRED_SIGNAL_KINDS",
    "SOURCE_DISPOSITIONS",
    "SourceIntegrityDecision",
    "TrainingIntegrityError",
    "TrainingIntegrityEvaluationEvidence",
    "TrainingIntegrityGate",
    "TrainingIntegrityReceipt",
    "TransformIdentity",
]
