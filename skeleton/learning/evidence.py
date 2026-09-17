"""Provider-neutral evidence-first learning contract.

The learning evidence plane stores raw observations/features separately from
derived hypotheses/predictions and explicit outcomes. It is intentionally
separate from curriculum/assessment and from Jeeves' read-only provider
grounding path.

Writes are explicit, provenance-bearing, versioned and rollback-capable.
Live-model/self-modifying sources are rejected. The contract is deterministic
when callers inject a deterministic clock.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from skeleton.kernel.errors import KernelError
from skeleton.retrieval.provenance import ProvenanceEntry

MAX_ID_CHARS = 256
MAX_CLAIM_CHARS = 4_096
MAX_SOURCE_CHARS = 256
MAX_PAYLOAD_KEYS = 64
DEFAULT_MAX_AGE_SECONDS = 3_600.0
DEFAULT_MAX_HISTORY = 64
DEFAULT_FUTURE_SKEW_SECONDS = 60.0
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


def _non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LearningEvidenceError(
            f"{name} must be a non-negative integer",
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


def _canonical_json_obj(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_obj(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple):
        return [_canonical_json_obj(item) for item in value]
    if isinstance(value, list):
        return [_canonical_json_obj(item) for item in value]
    return value


def _canonical_json(value: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(
        _canonical_json_obj(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        default=str,
    )


def canonical_fingerprint(payload: Mapping[str, object] | object) -> str:
    """Stable learning-plane fingerprint using canonical retrieval hashing."""
    return ProvenanceEntry.hash_data(_canonical_json(payload))


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
        frozen[name] = _json_scalar(f"payload[{name}]", value)
    return MappingProxyType(frozen)


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
    """Required chain-of-custody metadata for a learning record."""

    source_id: str
    source_kind: str
    observed_at: float
    clock_version: int
    fingerprint: str
    parent_ids: tuple[str, ...] = ()
    uri: str | None = None
    source_digest: str | None = None
    retrieved_at: float | None = None
    revision: str | None = None

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
        if self.source_digest is not None:
            object.__setattr__(self, "source_digest", _text("source_digest", self.source_digest, 128))
        if self.retrieved_at is not None:
            object.__setattr__(self, "retrieved_at", _non_negative("retrieved_at", self.retrieved_at))
        if self.revision is not None:
            object.__setattr__(self, "revision", _text("revision", self.revision, 128))


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    subject_id: str
    payload: Mapping[str, object]
    provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _text("observation_id", self.observation_id, MAX_ID_CHARS))
        object.__setattr__(self, "subject_id", _text("subject_id", self.subject_id, MAX_ID_CHARS))
        frozen = _freeze_payload(self.payload)
        _require_provenance(self.provenance, expected_fingerprint=canonical_fingerprint(frozen))
        object.__setattr__(self, "payload", frozen)
        if self.provenance.parent_ids:
            raise LearningEvidenceError(
                "observations are root facts and must not declare parents",
                context={"reason": "invalid_parent", "observation_id": self.observation_id},
            )


@dataclass(frozen=True, slots=True)
class Feature:
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


@dataclass(frozen=True, slots=True)
class Hypothesis:
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
                {"claim": self.claim, "polarity": self.polarity, "subject_id": self.subject_id}
            ),
        )
        _require_parents(self.provenance, self.feature_ids, record_id=self.hypothesis_id)


@dataclass(frozen=True, slots=True)
class Calibration:
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
        object.__setattr__(self, "sample_count", _non_negative_int("sample_count", self.sample_count))
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


@dataclass(frozen=True, slots=True)
class Prediction:
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


@dataclass(frozen=True, slots=True)
class Outcome:
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


@dataclass(frozen=True, slots=True)
class UpdateRecord:
    version: int
    kind: UpdateKind
    target_id: str
    timestamp: float
    previous_version: int | None = None
    reversible: bool = True

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
                _non_negative_int("previous_version", self.previous_version),
            )


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


def _require_provenance(
    provenance: EvidenceProvenance | None,
    *,
    expected_fingerprint: str,
) -> None:
    if provenance is None or not isinstance(provenance, EvidenceProvenance):
        raise LearningEvidenceError(
            "provenance is required and must be EvidenceProvenance",
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


def _sha256_for_evidence_data(payload: Any) -> str:
    rendered = _canonical_json(payload, ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def make_provenance_from_evidence_envelope(
    payload: Mapping[str, object] | object,
    provenance: Mapping[str, object],
    *,
    source_kind: str = "jeeves-evidence",
    clock_version: int = 1,
    parent_ids: tuple[str, ...] = (),
    uri: str | None = None,
) -> EvidenceProvenance:
    """Translate an EvidenceJeevesCore provenance envelope explicitly."""
    if not isinstance(provenance, Mapping):
        raise LearningEvidenceError(
            "evidence provenance envelope must be a mapping",
            context={"reason": "missing_provenance"},
        )

    source_id = _text("source_id", provenance.get("source_id"), MAX_SOURCE_CHARS)
    if "observed_at" not in provenance:
        raise LearningEvidenceError(
            "evidence provenance requires observed_at for learning ingestion",
            context={"reason": "missing_provenance", "field": "observed_at"},
        )
    observed_at = _non_negative("observed_at", provenance["observed_at"])

    digest = _text("sha256", provenance.get("sha256"), 64).casefold()
    expected = _sha256_for_evidence_data(payload)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise LearningEvidenceError(
            "evidence provenance sha256 is malformed",
            context={"reason": "fingerprint_mismatch", "algorithm": "sha256"},
        )
    if digest != expected:
        raise LearningEvidenceError(
            "evidence provenance sha256 does not match payload",
            context={"reason": "fingerprint_mismatch", "algorithm": "sha256"},
        )

    retrieved_at_raw = provenance.get("retrieved_at")
    retrieved_at = None if retrieved_at_raw is None else _non_negative("retrieved_at", retrieved_at_raw)
    revision_raw = provenance.get("revision")
    revision = None if revision_raw is None else _text("revision", revision_raw, 128)

    return EvidenceProvenance(
        source_id=source_id,
        source_kind=source_kind,
        observed_at=observed_at,
        clock_version=clock_version,
        fingerprint=canonical_fingerprint(payload),
        parent_ids=parent_ids,
        uri=uri,
        source_digest=digest,
        retrieved_at=retrieved_at,
        revision=revision,
    )


class LearningEvidenceStore:
    """Explicit, fail-closed, versioned store for learning evidence."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        clock_version: int = 1,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        max_history: int = DEFAULT_MAX_HISTORY,
        future_skew_seconds: float = DEFAULT_FUTURE_SKEW_SECONDS,
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
        self._future_skew_seconds = _non_negative("future_skew_seconds", future_skew_seconds)
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
        self._snapshots[0] = self._capture()

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
        return tuple(self._history)

    def calibration(self, channel: str) -> Calibration | None:
        return self._calibrations.get(_text("channel", channel, MAX_ID_CHARS))

    def plane_of(self, record_id: str) -> RecordPlane:
        record_id = _text("record_id", record_id, MAX_ID_CHARS)
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
        self._clock_version += 1
        return self._clock_version

    def record_observation(self, observation: Observation) -> UpdateRecord:
        timestamp = self._reject_stale(observation.provenance)
        self._reject_duplicate(observation.observation_id)
        self._observations[observation.observation_id] = observation
        return self._commit(UpdateKind.OBSERVATION, observation.observation_id, timestamp)

    def record_feature(self, feature: Feature) -> UpdateRecord:
        timestamp = self._reject_stale(feature.provenance)
        self._reject_duplicate(feature.feature_id)
        self._require_existing(feature.observation_ids, self._observations, kind="observation")
        self._reject_feature_contradiction(feature)
        self._features[feature.feature_id] = feature
        return self._commit(UpdateKind.FEATURE, feature.feature_id, timestamp)

    def record_hypothesis(self, hypothesis: Hypothesis) -> UpdateRecord:
        timestamp = self._reject_stale(hypothesis.provenance)
        self._reject_duplicate(hypothesis.hypothesis_id)
        self._require_existing(hypothesis.feature_ids, self._features, kind="feature")
        self._reject_hypothesis_contradiction(hypothesis)
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return self._commit(UpdateKind.HYPOTHESIS, hypothesis.hypothesis_id, timestamp)

    def record_prediction(self, prediction: Prediction) -> UpdateRecord:
        timestamp = self._reject_stale(prediction.provenance)
        self._reject_duplicate(prediction.prediction_id)
        self._require_existing((prediction.hypothesis_id,), self._hypotheses, kind="hypothesis")
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
        self._predictions[prediction.prediction_id] = prediction
        return self._commit(UpdateKind.PREDICTION, prediction.prediction_id, timestamp)

    def record_outcome(self, outcome: Outcome) -> UpdateRecord:
        timestamp = self._reject_stale(outcome.provenance)
        self._reject_duplicate(outcome.outcome_id)
        prediction = self._predictions.get(outcome.prediction_id)
        if prediction is None:
            raise LearningEvidenceError(
                "outcome cites an unknown prediction",
                context={"reason": "unknown_parent", "prediction_id": outcome.prediction_id},
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
        samples = self._samples.get(prediction.channel, ()) + ((prediction.confidence, outcome.correct),)
        self._samples[prediction.channel] = samples
        self._calibrations[prediction.channel] = _summarize_calibration(
            prediction.channel,
            samples,
            last_outcome_id=outcome.outcome_id,
            stated_confidence=prediction.confidence,
        )
        self._outcomes[outcome.outcome_id] = outcome
        return self._commit(UpdateKind.OUTCOME, outcome.outcome_id, timestamp)

    def rollback(self, version: int) -> UpdateRecord:
        version = _non_negative_int("version", version)
        snapshot = self._snapshots.get(version)
        if snapshot is None:
            raise LearningEvidenceError(
                "rollback target is outside bounded history",
                context={"reason": "rollback_unavailable", "version": version, "retained": sorted(self._snapshots)},
            )
        timestamp = _non_negative("clock", self._clock())
        self._restore(snapshot)
        return self._commit(UpdateKind.ROLLBACK, f"v{version}", timestamp)

    def lineage(self, record_id: str) -> tuple[str, ...]:
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
        if provenance.observed_at > now + self._future_skew_seconds:
            raise LearningEvidenceError(
                "evidence timestamp is implausibly ahead of the explicit clock",
                context={
                    "reason": "future_evidence",
                    "observed_at": provenance.observed_at,
                    "now": now,
                    "future_skew_seconds": self._future_skew_seconds,
                },
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
        newest_parent_time = 0.0
        for observation_id in feature.observation_ids:
            observation = self._observations[observation_id]
            subjects.add(observation.subject_id)
            newest_parent_time = max(newest_parent_time, observation.provenance.observed_at)
            if feature.name in observation.payload:
                cited_values.append(observation.payload[feature.name])
        if len(subjects) > 1 or feature.subject_id not in subjects:
            raise LearningEvidenceError(
                "feature subject must match cited observations",
                context={"reason": "subject_mismatch", "feature_id": feature.feature_id},
            )
        if feature.provenance.observed_at < newest_parent_time:
            raise LearningEvidenceError(
                "feature predates a cited observation",
                context={"reason": "stale_evidence", "feature_id": feature.feature_id},
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
                existing.subject_id != feature.subject_id
                or existing.name != feature.name
                or _values_equal(existing.value, feature.value)
            ):
                continue
            if feature.provenance.observed_at <= existing.provenance.observed_at:
                raise LearningEvidenceError(
                    "contradictory feature signal at the same or older observation time",
                    context={
                        "reason": "contradictory_signal",
                        "subject_id": feature.subject_id,
                        "name": feature.name,
                        "existing": existing.value,
                        "incoming": feature.value,
                        "existing_observed_at": existing.provenance.observed_at,
                        "incoming_observed_at": feature.provenance.observed_at,
                    },
                )

    def _reject_hypothesis_contradiction(self, hypothesis: Hypothesis) -> None:
        incoming_features = set(hypothesis.feature_ids)
        for existing in self._hypotheses.values():
            if existing.subject_id != hypothesis.subject_id:
                continue
            if existing.polarity == hypothesis.polarity:
                continue
            if incoming_features.isdisjoint(existing.feature_ids):
                continue
            raise LearningEvidenceError(
                "contradictory hypotheses over shared evidence",
                context={
                    "reason": "contradictory_signal",
                    "subject_id": hypothesis.subject_id,
                    "existing": existing.hypothesis_id,
                    "incoming": hypothesis.hypothesis_id,
                },
            )

    def _commit(self, kind: UpdateKind, target_id: str, timestamp: float) -> UpdateRecord:
        next_version = self._version + 1
        record = UpdateRecord(
            version=next_version,
            kind=kind,
            target_id=target_id,
            timestamp=timestamp,
            previous_version=self._version,
            reversible=True,
        )
        self._version = next_version
        self._history.append(record)
        self._snapshots[self._version] = self._capture()
        self._prune()
        return record

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
        if overflow > 0:
            self._history = self._history[overflow:]
        retained_versions = {record.version for record in self._history}
        if 1 in retained_versions:
            retained_versions.add(0)
        for version in tuple(self._snapshots):
            if version not in retained_versions:
                self._snapshots.pop(version, None)


def make_provenance(
    payload: Mapping[str, object] | object,
    *,
    source_id: str = "fixture",
    source_kind: str = "fixture",
    observed_at: float = 1_000.0,
    clock_version: int = 1,
    parent_ids: tuple[str, ...] = (),
    uri: str | None = None,
    source_digest: str | None = None,
    retrieved_at: float | None = None,
    revision: str | None = None,
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
        source_digest=source_digest,
        retrieved_at=retrieved_at,
        revision=revision,
    )
