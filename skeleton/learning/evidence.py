"""Provider-neutral evidence-first learning contract.

This module is the canonical home for Jeeves *learning* evidence: raw
observations, extracted features, hypotheses, predictions, outcomes,
calibration metadata, and bounded reversible update history.

It is intentionally distinct from:

* ``skeleton.learning.service`` — curriculum and Bloom assessment
* ``skeleton.jeeves.evidence_core`` — read-only tool evidence for LLM replies
* ``skeleton.jeeves.absorb`` / ``absorb_claims`` / ``absorb_evolution`` —
  absorb-plane intake, claims, and routing-policy evolution
* ``skeleton.retrieval.provenance`` — retrieval lineage ledger

Retrieval provenance is consumed (fingerprints), not replaced.  The store is
offline, deterministic when given an explicit clock, and fail-closed: missing
provenance, stale clock/version evidence, and contradictory signals are
rejected rather than averaged or silently repaired.  There is no path that
mutates the store from live model output; every write is an explicit caller
operation.
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from skeleton.kernel.errors import KernelError
from skeleton.retrieval.provenance import ProvenanceEntry

MAX_ID_CHARS = 128
MAX_CLAIM_CHARS = 4_096
MAX_SOURCE_CHARS = 256
MAX_PAYLOAD_KEYS = 64
DEFAULT_MAX_AGE_SECONDS = 3_600.0
DEFAULT_MAX_HISTORY = 64
BLOCKED_SOURCE_KINDS = frozenset(
    {
        "autonomous",
        "llm",
        "live-model",
        "model",
        "online",
        "self-modify",
        "self-modification",
    }
)


class LearningEvidenceError(KernelError):
    """Fail-closed contract violation for learning evidence."""

    code = "LRN.EVIDENCE"
    http_status = 422


class UpdateKind(str, Enum):
    OBSERVATION = "observation"
    FEATURE = "feature"
    HYPOTHESIS = "hypothesis"
    PREDICTION = "prediction"
    OUTCOME = "outcome"
    ROLLBACK = "rollback"


class RecordPlane(str, Enum):
    """Storage plane. Facts never share a map with derived analysis."""

    FACT = "fact"
    ANALYSIS = "analysis"
    RESULT = "result"


def _text(name: str, value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningEvidenceError(
            f"{name} must be a non-empty string",
            context={"field": name, "reason": "invalid_identifier"},
        )
    stripped = value.strip()
    if len(stripped) > maximum:
        raise LearningEvidenceError(
            f"{name} exceeds {maximum} characters",
            context={"field": name, "reason": "too_long", "max_chars": maximum},
        )
    return stripped


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LearningEvidenceError(
            f"{name} must be numeric",
            context={"field": name, "reason": "invalid_number"},
        )
    number = float(value)
    if not math.isfinite(number):
        raise LearningEvidenceError(
            f"{name} must be finite",
            context={"field": name, "reason": "invalid_number"},
        )
    return number


def _unit(name: str, value: Any) -> float:
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise LearningEvidenceError(
            f"{name} must be between 0 and 1",
            context={"field": name, "reason": "out_of_range"},
        )
    return number


def _non_negative(name: str, value: Any) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise LearningEvidenceError(
            f"{name} must be a non-negative finite number",
            context={"field": name, "reason": "invalid_number"},
        )
    return number


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LearningEvidenceError(
            f"{name} must be a positive integer",
            context={"field": name, "reason": "invalid_number"},
        )
    return value


def _json_scalar(name: str, value: Any) -> object:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LearningEvidenceError(
                f"{name} must be finite",
                context={"field": name, "reason": "invalid_number"},
            )
        return float(value)
    raise LearningEvidenceError(
        f"{name} must be a JSON scalar",
        context={"field": name, "reason": "unsupported_value"},
    )


def _canonical_json_value(value: Any) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LearningEvidenceError(
                "fingerprint payload contains non-finite number",
                context={"reason": "invalid_number"},
            )
        return float(value)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for raw_key, item in value.items():
            key = _text("fingerprint key", raw_key, MAX_ID_CHARS)
            if key in normalized:
                raise LearningEvidenceError(
                    "fingerprint keys collide after normalization",
                    context={"reason": "duplicate_key", "key": key},
                )
            normalized[key] = _canonical_json_value(item)
        return dict(sorted(normalized.items()))
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    raise LearningEvidenceError(
        "fingerprint payload contains unsupported value",
        context={"reason": "unsupported_value", "type": type(value).__name__},
    )


def canonical_fingerprint(payload: Mapping[str, object] | object) -> str:
    """Deterministic fingerprint that rejects unsupported runtime objects."""

    canonical = _canonical_json_value(payload)
    try:
        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LearningEvidenceError(
            "fingerprint payload is not deterministic JSON",
            context={"reason": "invalid_payload"},
        ) from exc
    return ProvenanceEntry.hash_data(encoded)


def _freeze_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise LearningEvidenceError(
            "payload must be a mapping of factual fields",
            context={"reason": "invalid_payload"},
        )
    if len(payload) > MAX_PAYLOAD_KEYS:
        raise LearningEvidenceError(
            "payload has too many keys",
            context={"reason": "payload_too_large", "max_keys": MAX_PAYLOAD_KEYS},
        )
    frozen: dict[str, object] = {}
    for key, value in payload.items():
        name = _text("payload key", key, MAX_ID_CHARS)
        if name in frozen:
            raise LearningEvidenceError(
                "payload keys collide after normalization",
                context={"reason": "duplicate_key", "key": name},
            )
        frozen[name] = _json_scalar(f"payload[{name}]", value)
    return MappingProxyType(dict(sorted(frozen.items())))


def _ids(name: str, values: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for raw in values:
        item = _text(name, raw, MAX_ID_CHARS)
        if item in seen:
            raise LearningEvidenceError(
                f"{name} contains duplicates",
                context={"field": name, "reason": "duplicate_parent"},
            )
        seen.append(item)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    """Required custody metadata for every learning evidence record."""

    source_id: str
    source_kind: str
    observed_at: float
    clock_version: int
    fingerprint: str
    parent_ids: tuple[str, ...] = ()
    uri: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id, MAX_SOURCE_CHARS))
        kind = _text("source_kind", self.source_kind, MAX_ID_CHARS).casefold()
        if kind in BLOCKED_SOURCE_KINDS:
            raise LearningEvidenceError(
                "live model or autonomous self-modification sources are rejected",
                context={"reason": "blocked_source", "source_kind": kind},
            )
        object.__setattr__(self, "source_kind", kind)
        object.__setattr__(self, "observed_at", _non_negative("observed_at", self.observed_at))
        object.__setattr__(self, "clock_version", _positive_int("clock_version", self.clock_version))
        object.__setattr__(self, "fingerprint", _text("fingerprint", self.fingerprint, 128))
        object.__setattr__(self, "parent_ids", _ids("parent_id", self.parent_ids))
        if self.uri is not None:
            object.__setattr__(self, "uri", _text("uri", self.uri, MAX_SOURCE_CHARS))

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "observed_at": self.observed_at,
            "clock_version": self.clock_version,
            "fingerprint": self.fingerprint,
            "parent_ids": list(self.parent_ids),
            "uri": self.uri,
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Observation:
    """Raw factual record. Stored on the fact plane, never mixed with analysis."""

    observation_id: str
    subject_id: str
    payload: Mapping[str, object]
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text("observation_id", self.observation_id, MAX_ID_CHARS))
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id, MAX_ID_CHARS))
        frozen = _freeze_payload(self.payload)
        object.__setattr__(self, "payload", frozen)
        _require_provenance(self.provenance, expected_fingerprint=canonical_fingerprint(frozen))
        if self.provenance.parent_ids:
            raise LearningEvidenceError(
                "observations are root facts and must not declare parents",
                context={"reason": "invalid_parent", "observation_id": self.observation_id},
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "subject_id": self.subject_id,
            "payload": dict(self.payload),
            "provenance": self.provenance.as_dict(),
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Feature:
    """Extracted measurement grounded in one or more observations."""

    feature_id: str
    subject_id: str
    name: str
    value: object
    observation_ids: tuple[str, ...]
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_id", _text("feature_id", self.feature_id, MAX_ID_CHARS))
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id, MAX_ID_CHARS))
        object.__setattr__(self, "name", _text("name", self.name, MAX_ID_CHARS))
        object.__setattr__(self, "value", _json_scalar("value", self.value))
        object.__setattr__(self, "observation_ids", _ids("observation_id", self.observation_ids))
        if not self.observation_ids:
            raise LearningEvidenceError(
                "features must cite at least one observation",
                context={"reason": "missing_parent", "feature_id": self.feature_id},
            )
        _require_provenance(
            self.provenance,
            expected_fingerprint=canonical_fingerprint(
                {"name": self.name, "value": self.value, "subject_id": self.subject_id}
            ),
        )
        _require_parents(self.provenance, self.observation_ids, record_id=self.feature_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "subject_id": self.subject_id,
            "name": self.name,
            "value": self.value,
            "observation_ids": list(self.observation_ids),
            "provenance": self.provenance.as_dict(),
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """Derived analysis. Stored on the analysis plane, never with raw facts."""

    hypothesis_id: str
    subject_id: str
    claim: str
    feature_ids: tuple[str, ...]
    confidence: float
    provenance: EvidenceProvenance
    polarity: str = "affirm"

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_id", _text("hypothesis_id", self.hypothesis_id, MAX_ID_CHARS))
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id, MAX_ID_CHARS))
        object.__setattr__(self, "claim", _text("claim", self.claim, MAX_CLAIM_CHARS))
        object.__setattr__(self, "feature_ids", _ids("feature_id", self.feature_ids))
        object.__setattr__(self, "confidence", _unit("confidence", self.confidence))
        polarity = _text("polarity", self.polarity, 32).casefold()
        if polarity not in {"affirm", "deny"}:
            raise LearningEvidenceError(
                "polarity must be affirm or deny",
                context={"reason": "invalid_polarity", "polarity": polarity},
            )
        object.__setattr__(self, "polarity", polarity)
        if not self.feature_ids:
            raise LearningEvidenceError(
                "hypotheses must cite at least one feature",
                context={"reason": "missing_parent", "hypothesis_id": self.hypothesis_id},
            )
        _require_provenance(
            self.provenance,
            expected_fingerprint=canonical_fingerprint(
                {
                    "claim": self.claim,
                    "polarity": self.polarity,
                    "subject_id": self.subject_id,
                }
            ),
        )
        _require_parents(self.provenance, self.feature_ids, record_id=self.hypothesis_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "subject_id": self.subject_id,
            "claim": self.claim,
            "feature_ids": list(self.feature_ids),
            "confidence": self.confidence,
            "polarity": self.polarity,
            "provenance": self.provenance.as_dict(),
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Calibration:
    """Confidence/calibration metadata. Never a substitute for factual payload."""

    channel: str
    stated_confidence: float
    empirical_rate: float
    sample_count: int
    expected_calibration_error: float
    last_outcome_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", _text("channel", self.channel, MAX_ID_CHARS))
        object.__setattr__(self, "stated_confidence", _unit("stated_confidence", self.stated_confidence))
        object.__setattr__(self, "empirical_rate", _unit("empirical_rate", self.empirical_rate))
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count < 0:
            raise LearningEvidenceError(
                "sample_count must be a non-negative integer",
                context={"reason": "invalid_number", "field": "sample_count"},
            )
        object.__setattr__(
            self,
            "expected_calibration_error",
            _unit("expected_calibration_error", self.expected_calibration_error),
        )
        if self.last_outcome_id is not None:
            object.__setattr__(
                self,
                "last_outcome_id",
                _text("last_outcome_id", self.last_outcome_id, MAX_ID_CHARS),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "stated_confidence": self.stated_confidence,
            "empirical_rate": self.empirical_rate,
            "sample_count": self.sample_count,
            "expected_calibration_error": self.expected_calibration_error,
            "last_outcome_id": self.last_outcome_id,
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Prediction:
    """Forward claim derived from a hypothesis, with calibration metadata."""

    prediction_id: str
    hypothesis_id: str
    expected: object
    confidence: float
    provenance: EvidenceProvenance
    calibration: Calibration
    channel: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "prediction_id", _text("prediction_id", self.prediction_id, MAX_ID_CHARS))
        object.__setattr__(self, "hypothesis_id", _text("hypothesis_id", self.hypothesis_id, MAX_ID_CHARS))
        object.__setattr__(self, "expected", _json_scalar("expected", self.expected))
        object.__setattr__(self, "confidence", _unit("confidence", self.confidence))
        object.__setattr__(self, "channel", _text("channel", self.channel, MAX_ID_CHARS))
        if self.calibration.channel != self.channel:
            raise LearningEvidenceError(
                "calibration channel must match prediction channel",
                context={"reason": "channel_mismatch", "prediction_id": self.prediction_id},
            )
        if self.calibration.stated_confidence != self.confidence:
            raise LearningEvidenceError(
                "calibration stated_confidence must match prediction confidence",
                context={"reason": "calibration_mismatch", "prediction_id": self.prediction_id},
            )
        _require_provenance(
            self.provenance,
            expected_fingerprint=canonical_fingerprint(
                {"hypothesis_id": self.hypothesis_id, "expected": self.expected}
            ),
        )
        _require_parents(self.provenance, (self.hypothesis_id,), record_id=self.prediction_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "prediction_id": self.prediction_id,
            "hypothesis_id": self.hypothesis_id,
            "expected": self.expected,
            "confidence": self.confidence,
            "channel": self.channel,
            "calibration": self.calibration.as_dict(),
            "provenance": self.provenance.as_dict(),
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class Outcome:
    """Observed result of a prediction. Does not rewrite the fact plane."""

    outcome_id: str
    prediction_id: str
    actual: object
    correct: bool
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome_id", _text("outcome_id", self.outcome_id, MAX_ID_CHARS))
        object.__setattr__(self, "prediction_id", _text("prediction_id", self.prediction_id, MAX_ID_CHARS))
        object.__setattr__(self, "actual", _json_scalar("actual", self.actual))
        if not isinstance(self.correct, bool):
            raise LearningEvidenceError(
                "correct must be a boolean",
                context={"reason": "invalid_outcome", "outcome_id": self.outcome_id},
            )
        _require_provenance(
            self.provenance,
            expected_fingerprint=canonical_fingerprint(
                {"prediction_id": self.prediction_id, "actual": self.actual, "correct": self.correct}
            ),
        )
        _require_parents(self.provenance, (self.prediction_id,), record_id=self.outcome_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome_id": self.outcome_id,
            "prediction_id": self.prediction_id,
            "actual": self.actual,
            "correct": self.correct,
            "provenance": self.provenance.as_dict(),
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class UpdateRecord:
    """One explicit, versioned mutation. History is bounded and reversible."""

    version: int
    kind: UpdateKind
    target_id: str
    timestamp: float
    previous_version: int | None = None
    reversible: bool = True
    state_digest: str | None = None
    previous_state_digest: str | None = None
    rollback_target_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _positive_int("version", self.version))
        if not isinstance(self.kind, UpdateKind):
            raise LearningEvidenceError(
                "kind must be an UpdateKind",
                context={"reason": "invalid_update"},
            )
        object.__setattr__(self, "target_id", _text("target_id", self.target_id, MAX_ID_CHARS))
        object.__setattr__(self, "timestamp", _non_negative("timestamp", self.timestamp))
        if self.previous_version is not None:
            object.__setattr__(
                self,
                "previous_version",
                _positive_int("previous_version", self.previous_version),
            )
        if not isinstance(self.reversible, bool):
            raise LearningEvidenceError(
                "reversible must be boolean",
                context={"reason": "invalid_update"},
            )
        for field_name in (
            "state_digest",
            "previous_state_digest",
            "rollback_target_digest",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(ch not in "0123456789abcdef" for ch in value)
                ):
                    raise LearningEvidenceError(
                        f"{field_name} must be lowercase sha256",
                        context={"reason": "invalid_update", "field": field_name},
                    )

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "kind": self.kind.value,
            "target_id": self.target_id,
            "timestamp": self.timestamp,
            "previous_version": self.previous_version,
            "reversible": self.reversible,
            "state_digest": self.state_digest,
            "previous_state_digest": self.previous_state_digest,
            "rollback_target_digest": self.rollback_target_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class _Snapshot:
    observations: dict[str, Observation]
    features: dict[str, Feature]
    hypotheses: dict[str, Hypothesis]
    predictions: dict[str, Prediction]
    outcomes: dict[str, Outcome]
    calibrations: dict[str, Calibration]
    samples: dict[str, tuple[tuple[float, bool], ...]]
    clock_version: int
    state_digest: str


@dataclass(frozen=True, slots=True)
class EvidenceStateReceipt:
    version: int
    clock_version: int
    state_digest: str
    history_digest: str
    observation_digests: tuple[str, ...]
    feature_digests: tuple[str, ...]
    hypothesis_digests: tuple[str, ...]
    prediction_digests: tuple[str, ...]
    outcome_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 0
        ):
            raise LearningEvidenceError(
                "state receipt version must be non-negative integer",
                context={"reason": "invalid_state_receipt"},
            )
        object.__setattr__(
            self,
            "clock_version",
            _positive_int("clock_version", self.clock_version),
        )
        for field_name in ("state_digest", "history_digest"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise LearningEvidenceError(
                    f"{field_name} must be lowercase sha256",
                    context={"reason": "invalid_state_receipt"},
                )
        for field_name in (
            "observation_digests",
            "feature_digests",
            "hypothesis_digests",
            "prediction_digests",
            "outcome_digests",
        ):
            values = tuple(getattr(self, field_name))
            if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
                for value in values
            ):
                raise LearningEvidenceError(
                    f"{field_name} contains invalid digest",
                    context={"reason": "invalid_state_receipt"},
                )
            object.__setattr__(self, field_name, values)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_evidence_state.v1",
            "version": self.version,
            "clock_version": self.clock_version,
            "state_digest": self.state_digest,
            "history_digest": self.history_digest,
            "observation_digests": list(self.observation_digests),
            "feature_digests": list(self.feature_digests),
            "hypothesis_digests": list(self.hypothesis_digests),
            "prediction_digests": list(self.prediction_digests),
            "outcome_digests": list(self.outcome_digests),
        }

    @property
    def receipt_digest(self) -> str:
        return canonical_fingerprint(self.as_dict())


def _require_provenance(
    provenance: EvidenceProvenance | None,
    *,
    expected_fingerprint: str,
) -> None:
    if provenance is None:
        raise LearningEvidenceError(
            "provenance is required",
            context={"reason": "missing_provenance"},
        )
    if not isinstance(provenance, EvidenceProvenance):
        raise LearningEvidenceError(
            "provenance must be EvidenceProvenance",
            context={"reason": "missing_provenance"},
        )
    if provenance.fingerprint != expected_fingerprint:
        raise LearningEvidenceError(
            "provenance fingerprint does not match payload",
            context={"reason": "fingerprint_mismatch"},
        )


def _require_parents(
    provenance: EvidenceProvenance,
    required: Iterable[str],
    *,
    record_id: str,
) -> None:
    missing = [parent for parent in required if parent not in provenance.parent_ids]
    if missing:
        raise LearningEvidenceError(
            "provenance parent_ids must include every cited predecessor",
            context={"reason": "missing_provenance", "record_id": record_id, "missing": missing},
        )


def _values_equal(left: object, right: object) -> bool:
    return canonical_fingerprint({"v": left}) == canonical_fingerprint({"v": right})


def empty_calibration(channel: str, stated_confidence: float) -> Calibration:
    return Calibration(
        channel=channel,
        stated_confidence=stated_confidence,
        empirical_rate=0.0,
        sample_count=0,
        expected_calibration_error=0.0,
    )


def _summarize_calibration(
    channel: str,
    samples: tuple[tuple[float, bool], ...],
    *,
    last_outcome_id: str | None,
    stated_confidence: float,
) -> Calibration:
    if not samples:
        return empty_calibration(channel, stated_confidence)
    hits = sum(1 for _, correct in samples if correct)
    empirical = hits / len(samples)
    mean_stated = sum(stated for stated, _ in samples) / len(samples)
    return Calibration(
        channel=channel,
        stated_confidence=stated_confidence,
        empirical_rate=empirical,
        sample_count=len(samples),
        expected_calibration_error=abs(mean_stated - empirical),
        last_outcome_id=last_outcome_id,
    )


class LearningEvidenceStore:
    """Explicit, versioned store for learning evidence.

    Raw observations and features live on the fact plane. Hypotheses and
    predictions live on the analysis plane. Outcomes are results. The three
    planes never share maps, so factual evidence cannot be overwritten by
    derived analysis.

    Callers inject a clock and a clock version. Incoming records whose
    ``observed_at`` is older than ``max_age_seconds`` or whose
    ``clock_version`` is below the store epoch are rejected as stale.
    Contradictory features or hypotheses fail closed instead of being
    averaged. Update history is bounded; rollback to an evicted version
    fails closed.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        clock_version: int = 1,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        max_history: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        if not callable(clock):
            raise LearningEvidenceError(
                "clock must be callable",
                context={"reason": "invalid_clock"},
            )
        self._clock = clock
        self._clock_version = _positive_int("clock_version", clock_version)
        self._max_age_seconds = _finite("max_age_seconds", max_age_seconds)
        if self._max_age_seconds <= 0.0:
            raise LearningEvidenceError(
                "max_age_seconds must be positive",
                context={"reason": "invalid_number"},
            )
        self._max_history = _positive_int("max_history", max_history)
        self._observations: dict[str, Observation] = {}
        self._features: dict[str, Feature] = {}
        self._hypotheses: dict[str, Hypothesis] = {}
        self._predictions: dict[str, Prediction] = {}
        self._outcomes: dict[str, Outcome] = {}
        self._calibrations: dict[str, Calibration] = {}
        self._samples: dict[str, tuple[tuple[float, bool], ...]] = {}
        self._history: list[UpdateRecord] = []
        self._snapshots: dict[int, _Snapshot] = {}
        self._version = 0
        self._lock = threading.RLock()

    @property
    def version(self) -> int:
        return self._version

    @property
    def clock_version(self) -> int:
        return self._clock_version

    @property
    def max_history(self) -> int:
        return self._max_history

    def facts(self) -> Mapping[str, Observation | Feature]:
        merged: dict[str, Observation | Feature] = {}
        merged.update(self._observations)
        merged.update(self._features)
        return dict(merged)

    def analysis(self) -> Mapping[str, Hypothesis | Prediction]:
        merged: dict[str, Hypothesis | Prediction] = {}
        merged.update(self._hypotheses)
        merged.update(self._predictions)
        return dict(merged)

    def results(self) -> Mapping[str, Outcome]:
        return dict(self._outcomes)

    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._observations[key] for key in sorted(self._observations))

    def features(self) -> tuple[Feature, ...]:
        return tuple(self._features[key] for key in sorted(self._features))

    def hypotheses(self) -> tuple[Hypothesis, ...]:
        return tuple(self._hypotheses[key] for key in sorted(self._hypotheses))

    def predictions(self) -> tuple[Prediction, ...]:
        return tuple(self._predictions[key] for key in sorted(self._predictions))

    def outcomes(self) -> tuple[Outcome, ...]:
        return tuple(self._outcomes[key] for key in sorted(self._outcomes))

    def history(self) -> tuple[UpdateRecord, ...]:
        with self._lock:
            return tuple(self._history)

    def state_digest(self) -> str:
        with self._lock:
            return self._state_digest()

    def state_receipt(self) -> EvidenceStateReceipt:
        with self._lock:
            observations = tuple(
                self._observations[key].digest
                for key in sorted(self._observations)
            )
            features = tuple(
                self._features[key].digest
                for key in sorted(self._features)
            )
            hypotheses = tuple(
                self._hypotheses[key].digest
                for key in sorted(self._hypotheses)
            )
            predictions = tuple(
                self._predictions[key].digest
                for key in sorted(self._predictions)
            )
            outcomes = tuple(
                self._outcomes[key].digest
                for key in sorted(self._outcomes)
            )
            history_digest = canonical_fingerprint(
                [record.as_dict() for record in self._history]
            )
            return EvidenceStateReceipt(
                version=self._version,
                clock_version=self._clock_version,
                state_digest=self._state_digest(),
                history_digest=history_digest,
                observation_digests=observations,
                feature_digests=features,
                hypothesis_digests=hypotheses,
                prediction_digests=predictions,
                outcome_digests=outcomes,
            )

    def verify_state_receipt(self, receipt: EvidenceStateReceipt) -> bool:
        if not isinstance(receipt, EvidenceStateReceipt):
            raise TypeError("receipt must be EvidenceStateReceipt")
        with self._lock:
            return receipt == self.state_receipt()

    def calibration(self, channel: str) -> Calibration | None:
        return self._calibrations.get(_text("channel", channel, MAX_ID_CHARS))

    def plane_of(self, record_id: str) -> RecordPlane:
        if record_id in self._observations or record_id in self._features:
            return RecordPlane.FACT
        if record_id in self._hypotheses or record_id in self._predictions:
            return RecordPlane.ANALYSIS
        if record_id in self._outcomes:
            return RecordPlane.RESULT
        raise LearningEvidenceError(
            "unknown record",
            context={"reason": "unknown_record", "record_id": record_id},
        )

    def advance_clock_version(self) -> int:
        """Explicit epoch bump. Prior clock versions become stale on ingest."""

        with self._lock:
            self._clock_version += 1
            return self._clock_version

    def record_observation(self, observation: Observation) -> UpdateRecord:
        with self._lock:
            commit_time = self._reject_stale(observation.provenance)
            self._reject_duplicate(observation.observation_id)
            previous_state = self._state_digest()
            self._observations[observation.observation_id] = observation
            return self._commit(
                UpdateKind.OBSERVATION,
                observation.observation_id,
                timestamp=commit_time,
                previous_state_digest=previous_state,
            )

    def record_feature(self, feature: Feature) -> UpdateRecord:
        with self._lock:
            commit_time = self._reject_stale(feature.provenance)
            self._reject_duplicate(feature.feature_id)
            self._require_existing(
                feature.observation_ids,
                self._observations,
                kind="observation",
            )
            self._reject_feature_contradiction(feature)
            previous_state = self._state_digest()
            self._features[feature.feature_id] = feature
            return self._commit(
                UpdateKind.FEATURE,
                feature.feature_id,
                timestamp=commit_time,
                previous_state_digest=previous_state,
            )

    def record_hypothesis(self, hypothesis: Hypothesis) -> UpdateRecord:
        with self._lock:
            commit_time = self._reject_stale(hypothesis.provenance)
            self._reject_duplicate(hypothesis.hypothesis_id)
            self._require_existing(
                hypothesis.feature_ids,
                self._features,
                kind="feature",
            )
            mismatched = [
                feature_id
                for feature_id in hypothesis.feature_ids
                if self._features[feature_id].subject_id != hypothesis.subject_id
            ]
            if mismatched:
                raise LearningEvidenceError(
                    "hypothesis subject must match every cited feature",
                    context={
                        "reason": "subject_mismatch",
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "mismatched_features": mismatched,
                    },
                )
            self._reject_hypothesis_contradiction(hypothesis)
            previous_state = self._state_digest()
            self._hypotheses[hypothesis.hypothesis_id] = hypothesis
            return self._commit(
                UpdateKind.HYPOTHESIS,
                hypothesis.hypothesis_id,
                timestamp=commit_time,
                previous_state_digest=previous_state,
            )

    def record_prediction(self, prediction: Prediction) -> UpdateRecord:
        with self._lock:
            commit_time = self._reject_stale(prediction.provenance)
            self._reject_duplicate(prediction.prediction_id)
            self._require_existing(
                (prediction.hypothesis_id,),
                self._hypotheses,
                kind="hypothesis",
            )
            existing = [
                item
                for item in self._predictions.values()
                if item.hypothesis_id == prediction.hypothesis_id
                and not _values_equal(item.expected, prediction.expected)
            ]
            if existing:
                raise LearningEvidenceError(
                    "contradictory prediction for the same hypothesis",
                    context={
                        "reason": "contradictory_signal",
                        "hypothesis_id": prediction.hypothesis_id,
                        "existing": existing[0].expected,
                        "incoming": prediction.expected,
                    },
                )
            previous_state = self._state_digest()
            self._predictions[prediction.prediction_id] = prediction
            return self._commit(
                UpdateKind.PREDICTION,
                prediction.prediction_id,
                timestamp=commit_time,
                previous_state_digest=previous_state,
            )

    def record_outcome(self, outcome: Outcome) -> UpdateRecord:
        with self._lock:
            commit_time = self._reject_stale(outcome.provenance)
            self._reject_duplicate(outcome.outcome_id)
            prediction = self._predictions.get(outcome.prediction_id)
            if prediction is None:
                raise LearningEvidenceError(
                    "outcome cites an unknown prediction",
                    context={
                        "reason": "unknown_parent",
                        "prediction_id": outcome.prediction_id,
                    },
                )
            derived = _values_equal(outcome.actual, prediction.expected)
            if outcome.correct is not derived:
                raise LearningEvidenceError(
                    "outcome.correct contradicts the prediction comparison",
                    context={
                        "reason": "contradictory_signal",
                        "outcome_id": outcome.outcome_id,
                        "expected": prediction.expected,
                        "actual": outcome.actual,
                    },
                )
            previous_state = self._state_digest()
            samples = self._samples.get(prediction.channel, ()) + (
                (prediction.confidence, outcome.correct),
            )
            self._samples[prediction.channel] = samples
            self._calibrations[prediction.channel] = _summarize_calibration(
                prediction.channel,
                samples,
                last_outcome_id=outcome.outcome_id,
                stated_confidence=prediction.confidence,
            )
            self._outcomes[outcome.outcome_id] = outcome
            return self._commit(
                UpdateKind.OUTCOME,
                outcome.outcome_id,
                timestamp=commit_time,
                previous_state_digest=previous_state,
            )

    def rollback(
        self,
        version: int,
        *,
        expected_state_digest: str | None = None,
    ) -> UpdateRecord:
        with self._lock:
            snapshot = self._snapshots.get(version)
            if snapshot is None:
                raise LearningEvidenceError(
                    "rollback target is outside bounded history",
                    context={
                        "reason": "rollback_unavailable",
                        "version": version,
                        "retained": sorted(self._snapshots),
                    },
                )
            if (
                expected_state_digest is not None
                and expected_state_digest != snapshot.state_digest
            ):
                raise LearningEvidenceError(
                    "rollback target state digest mismatch",
                    context={
                        "reason": "rollback_identity_mismatch",
                        "version": version,
                    },
                )
            commit_time = _non_negative("clock", self._clock())
            previous_state = self._state_digest()
            self._restore(snapshot)
            return self._commit(
                UpdateKind.ROLLBACK,
                f"v{version}",
                timestamp=commit_time,
                previous_state_digest=previous_state,
                rollback_target_digest=snapshot.state_digest,
            )

    def lineage(self, record_id: str) -> tuple[str, ...]:
        """Walk provenance parents from roots to ``record_id``."""

        ordered: list[str] = []
        visiting: set[str] = set()

        def walk(current: str) -> None:
            if current in visiting:
                raise LearningEvidenceError(
                    "provenance cycle",
                    context={"reason": "cycle", "record_id": current},
                )
            if current in ordered:
                return
            visiting.add(current)
            record = self._lookup(current)
            for parent in record.provenance.parent_ids:
                walk(parent)
            visiting.remove(current)
            ordered.append(current)

        walk(_text("record_id", record_id, MAX_ID_CHARS))
        return tuple(ordered)

    def _lookup(self, record_id: str) -> Observation | Feature | Hypothesis | Prediction | Outcome:
        for pool in (
            self._observations,
            self._features,
            self._hypotheses,
            self._predictions,
            self._outcomes,
        ):
            record = pool.get(record_id)
            if record is not None:
                return record
        raise LearningEvidenceError(
            "unknown record",
            context={"reason": "unknown_record", "record_id": record_id},
        )

    def _reject_stale(self, provenance: EvidenceProvenance) -> float:
        now = _non_negative("clock", self._clock())
        age = now - provenance.observed_at
        if age > self._max_age_seconds:
            raise LearningEvidenceError(
                "evidence is stale against the explicit clock",
                context={
                    "reason": "stale_evidence",
                    "age": age,
                    "max_age_seconds": self._max_age_seconds,
                    "observed_at": provenance.observed_at,
                    "now": now,
                },
            )
        if provenance.observed_at > now:
            raise LearningEvidenceError(
                "evidence timestamp is ahead of the explicit clock",
                context={"reason": "stale_evidence", "observed_at": provenance.observed_at, "now": now},
            )
        if provenance.clock_version != self._clock_version:
            raise LearningEvidenceError(
                "evidence is stale against the explicit clock version",
                context={
                    "reason": "stale_evidence",
                    "clock_version": provenance.clock_version,
                    "store_clock_version": self._clock_version,
                },
            )
        return now

    def _reject_duplicate(self, record_id: str) -> None:
        if (
            record_id in self._observations
            or record_id in self._features
            or record_id in self._hypotheses
            or record_id in self._predictions
            or record_id in self._outcomes
        ):
            raise LearningEvidenceError(
                "record id already exists",
                context={"reason": "duplicate_id", "record_id": record_id},
            )

    def _require_existing(self, ids: Iterable[str], pool: Mapping[str, object], *, kind: str) -> None:
        missing = [item for item in ids if item not in pool]
        if missing:
            raise LearningEvidenceError(
                f"{kind} parent is missing",
                context={"reason": "unknown_parent", "missing": missing},
            )

    def _reject_feature_contradiction(self, feature: Feature) -> None:
        cited_values: list[object] = []
        subjects: set[str] = set()
        for observation_id in feature.observation_ids:
            observation = self._observations[observation_id]
            subjects.add(observation.subject_id)
            if feature.name in observation.payload:
                cited_values.append(observation.payload[feature.name])
        if len(subjects) > 1 or feature.subject_id not in subjects:
            raise LearningEvidenceError(
                "feature subject must match cited observations",
                context={"reason": "subject_mismatch", "feature_id": feature.feature_id},
            )
        unique_cited = {canonical_fingerprint({"v": value}) for value in cited_values}
        if len(unique_cited) > 1:
            raise LearningEvidenceError(
                "cited observations contain contradictory signals",
                context={"reason": "contradictory_signal", "feature_id": feature.feature_id},
            )
        if unique_cited and canonical_fingerprint({"v": feature.value}) not in unique_cited:
            raise LearningEvidenceError(
                "feature value contradicts cited observations",
                context={"reason": "contradictory_signal", "feature_id": feature.feature_id},
            )
        for existing in self._features.values():
            if (
                existing.subject_id == feature.subject_id
                and existing.name == feature.name
                and not _values_equal(existing.value, feature.value)
            ):
                raise LearningEvidenceError(
                    "contradictory feature signal; values are not averaged",
                    context={
                        "reason": "contradictory_signal",
                        "subject_id": feature.subject_id,
                        "name": feature.name,
                        "existing": existing.value,
                        "incoming": feature.value,
                    },
                )

    def _reject_hypothesis_contradiction(self, hypothesis: Hypothesis) -> None:
        for existing in self._hypotheses.values():
            if existing.subject_id != hypothesis.subject_id:
                continue
            if existing.polarity != hypothesis.polarity:
                raise LearningEvidenceError(
                    "contradictory hypotheses; signals are not averaged",
                    context={
                        "reason": "contradictory_signal",
                        "subject_id": hypothesis.subject_id,
                        "existing": existing.hypothesis_id,
                        "incoming": hypothesis.hypothesis_id,
                    },
                )

    def _commit(
        self,
        kind: UpdateKind,
        target_id: str,
        *,
        timestamp: float,
        previous_state_digest: str | None = None,
        rollback_target_digest: str | None = None,
    ) -> UpdateRecord:
        """Append one already-validated mutation to the bounded journal.

        Callers must sample/validate time before mutating their plane. Construct
        the immutable record before advancing the store version so validation
        failures cannot create version gaps.
        """
        previous = self._version if self._version > 0 else None
        new_version = self._version + 1
        before_digest = (
            previous_state_digest
            if previous_state_digest is not None
            else self._state_digest()
        )
        self._version = new_version
        after_digest = self._state_digest()
        record = UpdateRecord(
            version=new_version,
            kind=kind,
            target_id=target_id,
            timestamp=timestamp,
            previous_version=previous,
            reversible=True,
            state_digest=after_digest,
            previous_state_digest=before_digest,
            rollback_target_digest=rollback_target_digest,
        )
        self._history.append(record)
        self._snapshots[new_version] = self._capture()
        self._prune()
        return record

    def _state_payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.learning_evidence_store_state.v1",
            "version": self._version,
            "clock_version": self._clock_version,
            "observations": [
                [key, self._observations[key].digest]
                for key in sorted(self._observations)
            ],
            "features": [
                [key, self._features[key].digest]
                for key in sorted(self._features)
            ],
            "hypotheses": [
                [key, self._hypotheses[key].digest]
                for key in sorted(self._hypotheses)
            ],
            "predictions": [
                [key, self._predictions[key].digest]
                for key in sorted(self._predictions)
            ],
            "outcomes": [
                [key, self._outcomes[key].digest]
                for key in sorted(self._outcomes)
            ],
            "calibrations": [
                [key, self._calibrations[key].digest]
                for key in sorted(self._calibrations)
            ],
            "samples": [
                [
                    key,
                    [
                        [confidence, correct]
                        for confidence, correct in self._samples[key]
                    ],
                ]
                for key in sorted(self._samples)
            ],
        }

    def _state_digest(self) -> str:
        return canonical_fingerprint(self._state_payload())

    def _capture(self) -> _Snapshot:
        return _Snapshot(
            observations=dict(self._observations),
            features=dict(self._features),
            hypotheses=dict(self._hypotheses),
            predictions=dict(self._predictions),
            outcomes=dict(self._outcomes),
            calibrations=dict(self._calibrations),
            samples=dict(self._samples),
            clock_version=self._clock_version,
            state_digest=self._state_digest(),
        )

    def _restore(self, snapshot: _Snapshot) -> None:
        self._observations = dict(snapshot.observations)
        self._features = dict(snapshot.features)
        self._hypotheses = dict(snapshot.hypotheses)
        self._predictions = dict(snapshot.predictions)
        self._outcomes = dict(snapshot.outcomes)
        self._calibrations = dict(snapshot.calibrations)
        self._samples = dict(snapshot.samples)
        self._clock_version = snapshot.clock_version

    def _prune(self) -> None:
        overflow = len(self._history) - self._max_history
        if overflow <= 0:
            return
        evicted = self._history[:overflow]
        self._history = self._history[overflow:]
        for record in evicted:
            self._snapshots.pop(record.version, None)


def make_provenance(
    payload: Mapping[str, object] | object,
    *,
    source_id: str = "fixture",
    source_kind: str = "fixture",
    observed_at: float = 1_000.0,
    clock_version: int = 1,
    parent_ids: tuple[str, ...] = (),
    uri: str | None = None,
) -> EvidenceProvenance:
    """Deterministic offline provenance helper for fixtures and callers."""

    return EvidenceProvenance(
        source_id=source_id,
        source_kind=source_kind,
        observed_at=observed_at,
        clock_version=clock_version,
        fingerprint=canonical_fingerprint(payload),
        parent_ids=parent_ids,
        uri=uri,
    )
