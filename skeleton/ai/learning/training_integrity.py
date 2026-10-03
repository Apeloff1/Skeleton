"""Fail-closed training-data integrity admission.

This control plane turns poisoning/backdoor concerns into executable admission
rules.  It does not attempt to prove a corpus is benign; it requires immutable
transform identity, source dispositions, anomaly evidence and trigger-canary
coverage before a dataset can be admitted to a training run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
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

    @property
    def identity(self) -> str:
        return "transform:" + _digest(
            {
                "transform_id": self.transform_id,
                "implementation_digest": self.implementation_digest,
                "configuration_digest": self.configuration_digest,
                "signer_ref": self.signer_ref,
            }
        )


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
            if not 0.0 <= float(self.score) <= 1.0:
                raise TrainingIntegrityError("score must be in [0, 1]")
            object.__setattr__(self, "score", float(self.score))

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
        object.__setattr__(self, "signal_digests", values)
        object.__setattr__(self, "rationale", _text("rationale", self.rationale))


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
        transforms = tuple(_text("transform identity", item) for item in self.transform_identities)
        if len(transforms) != len(set(transforms)):
            raise TrainingIntegrityError("transform identities must be unique")
        object.__setattr__(self, "transform_identities", transforms)
        if not self.source_decisions:
            raise TrainingIntegrityError("source decisions must not be empty")
        ids = [item.source_id for item in self.source_decisions]
        if len(ids) != len(set(ids)):
            raise TrainingIntegrityError("source decisions must be unique")
        signals = tuple(_sha("signal_digest", item) for item in self.signal_digests)
        if len(signals) != len(set(signals)):
            raise TrainingIntegrityError("signal digests must be unique")
        object.__setattr__(self, "signal_digests", signals)
        if not isinstance(self.admitted, bool):
            raise TypeError("admitted must be boolean")
        if self.admitted and any(item.disposition != "admit" for item in self.source_decisions):
            raise TrainingIntegrityError("admitted dataset contains non-admitted source")
        frozen = dict(self.metadata)
        _json(frozen)
        object.__setattr__(self, "metadata", frozen)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.training_integrity_receipt.v1",
                "dataset_id": self.dataset_id,
                "dataset_digest": self.dataset_digest,
                "transform_identities": list(self.transform_identities),
                "source_decisions": [
                    {
                        "source_id": item.source_id,
                        "source_digest": item.source_digest,
                        "disposition": item.disposition,
                        "signal_digests": list(item.signal_digests),
                        "rationale": item.rationale,
                    }
                    for item in self.source_decisions
                ],
                "signal_digests": list(self.signal_digests),
                "admitted": self.admitted,
                "policy_digest": self.policy_digest,
                "metadata": dict(self.metadata),
            }
        )


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

        source_map = {
            _text("source_id", source_id): _sha("source_digest", digest)
            for source_id, digest in source_digests.items()
        }
        by_source: dict[str, list[IntegritySignal]] = {source_id: [] for source_id in source_map}
        for signal in signals:
            if not isinstance(signal, IntegritySignal):
                raise TypeError("signals must contain IntegritySignal values")
            if signal.source_id not in by_source:
                raise TrainingIntegrityError("integrity signal references unknown source")
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
            transform_identities=tuple(item.identity for item in transforms),
            source_decisions=tuple(decisions),
            signal_digests=tuple(sorted(set(all_signal_digests))),
            admitted=admitted,
            policy_digest=self.policy_digest,
        )

    @staticmethod
    def require_admitted(receipt: TrainingIntegrityReceipt) -> None:
        if not isinstance(receipt, TrainingIntegrityReceipt):
            raise TypeError("receipt must be TrainingIntegrityReceipt")
        if not receipt.admitted:
            raise TrainingIntegrityError("dataset is quarantined and cannot enter training")


__all__ = [
    "IntegritySignal",
    "REQUIRED_SIGNAL_KINDS",
    "SOURCE_DISPOSITIONS",
    "SourceIntegrityDecision",
    "TrainingIntegrityError",
    "TrainingIntegrityGate",
    "TrainingIntegrityReceipt",
    "TransformIdentity",
]
