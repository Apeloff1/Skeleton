"""Fail-closed Jeeves market evidence and response authority.

This bounded VOL-072 surface keeps factual market observations distinct from
analysis and prediction, preserves source/timestamp provenance, rejects stale
or future evidence, and emits a deterministic receipt that binds the response
to the exact evidence set and freshness policy.

Models may propose derived records. Only this deterministic boundary decides
whether those records are eligible for a governed Jeeves response.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping
from urllib.parse import urlparse

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_MAX_SUMMARY_CHARS = 4096
_MAX_EVIDENCE_RECORDS = 512


class JeevesEvidenceError(ValueError):
    """Evidence or response material failed a governed Jeeves contract."""


class JeevesEvidenceKind(str, Enum):
    MARKET_FACT = "market_fact"
    ANALYSIS = "analysis"
    PREDICTION = "prediction"


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise JeevesEvidenceError(f"{field} must be a non-empty RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise JeevesEvidenceError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise JeevesEvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _require_identifier(value: str | None, *, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise JeevesEvidenceError(f"{field} is not a canonical identifier")
    return value


def _require_digest(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise JeevesEvidenceError(f"{field} must be lowercase canonical sha256")
    return value


def _require_source_uri(value: str | None) -> str:
    if not isinstance(value, str):
        raise JeevesEvidenceError("source_uri is required for market facts")
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if parsed.scheme == "urn" and parsed.path:
        return value
    raise JeevesEvidenceError("source_uri must be an https URL or explicit urn")


@dataclass(frozen=True, slots=True)
class JeevesFreshnessPolicy:
    max_age_seconds: int
    max_future_skew_seconds: int = 5

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_age_seconds, bool)
            or not isinstance(self.max_age_seconds, int)
            or self.max_age_seconds <= 0
        ):
            raise JeevesEvidenceError("max_age_seconds must be a positive integer")
        if (
            isinstance(self.max_future_skew_seconds, bool)
            or not isinstance(self.max_future_skew_seconds, int)
            or not 0 <= self.max_future_skew_seconds <= 300
        ):
            raise JeevesEvidenceError(
                "max_future_skew_seconds must be an integer between 0 and 300"
            )


@dataclass(frozen=True, slots=True)
class JeevesEvidenceRecord:
    evidence_id: str
    kind: JeevesEvidenceKind
    summary: str
    content_digest: str
    depends_on: tuple[str, ...] = ()
    source_id: str | None = None
    source_uri: str | None = None
    observed_at: str | None = None
    valid_until: str | None = None
    confidence: float | None = None
    prediction_horizon_seconds: int | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.evidence_id, field="evidence_id")
        if not isinstance(self.kind, JeevesEvidenceKind):
            raise JeevesEvidenceError("kind must be JeevesEvidenceKind")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise JeevesEvidenceError("summary must be non-empty")
        if len(self.summary) > _MAX_SUMMARY_CHARS:
            raise JeevesEvidenceError("summary exceeds bounded response size")
        _require_digest(self.content_digest, field="content_digest")

        dependencies = tuple(self.depends_on)
        if len(dependencies) != len(set(dependencies)):
            raise JeevesEvidenceError("depends_on contains duplicate identities")
        for dependency in dependencies:
            _require_identifier(dependency, field="depends_on")
            if dependency == self.evidence_id:
                raise JeevesEvidenceError("evidence cannot depend on itself")
        object.__setattr__(self, "depends_on", dependencies)

        if self.confidence is not None:
            if (
                isinstance(self.confidence, bool)
                or not isinstance(self.confidence, (int, float))
                or not math.isfinite(float(self.confidence))
                or not 0.0 <= float(self.confidence) <= 1.0
            ):
                raise JeevesEvidenceError("confidence must be finite and within [0, 1]")

        if self.kind is JeevesEvidenceKind.MARKET_FACT:
            if dependencies:
                raise JeevesEvidenceError("market facts cannot depend on derived evidence")
            _require_identifier(self.source_id, field="source_id")
            _require_source_uri(self.source_uri)
            _parse_timestamp(self.observed_at or "", field="observed_at")
            if self.valid_until is not None:
                _parse_timestamp(self.valid_until, field="valid_until")
            if self.confidence is not None:
                raise JeevesEvidenceError("market facts must not smuggle analysis confidence")
            if self.prediction_horizon_seconds is not None:
                raise JeevesEvidenceError("market facts cannot carry a prediction horizon")
            return

        if self.source_id is not None or self.source_uri is not None or self.observed_at is not None:
            raise JeevesEvidenceError(
                "derived records inherit provenance through dependencies; fact source fields are forbidden"
            )
        if self.valid_until is not None:
            raise JeevesEvidenceError("derived records cannot carry market-fact validity windows")
        if not dependencies:
            raise JeevesEvidenceError("derived evidence requires dependencies")

        if self.kind is JeevesEvidenceKind.ANALYSIS:
            if self.prediction_horizon_seconds is not None:
                raise JeevesEvidenceError("analysis cannot carry prediction horizon")
            return

        if self.confidence is None:
            raise JeevesEvidenceError("prediction confidence is required")
        if (
            isinstance(self.prediction_horizon_seconds, bool)
            or not isinstance(self.prediction_horizon_seconds, int)
            or self.prediction_horizon_seconds <= 0
        ):
            raise JeevesEvidenceError("prediction_horizon_seconds must be a positive integer")


@dataclass(frozen=True, slots=True)
class JeevesEvidenceResponse:
    generated_at: str
    facts: tuple[JeevesEvidenceRecord, ...]
    analyses: tuple[JeevesEvidenceRecord, ...]
    predictions: tuple[JeevesEvidenceRecord, ...]
    receipt_digest: str

    def records(self) -> tuple[JeevesEvidenceRecord, ...]:
        return self.facts + self.analyses + self.predictions

    def to_wire(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "facts": [_record_payload(item) for item in self.facts],
            "analyses": [_record_payload(item) for item in self.analyses],
            "predictions": [_record_payload(item) for item in self.predictions],
            "receipt_digest": self.receipt_digest,
        }


def _record_payload(item: JeevesEvidenceRecord) -> dict[str, object]:
    return {
        "evidence_id": item.evidence_id,
        "kind": item.kind.value,
        "summary": item.summary,
        "content_digest": item.content_digest,
        "depends_on": list(item.depends_on),
        "source_id": item.source_id,
        "source_uri": item.source_uri,
        "observed_at": item.observed_at,
        "valid_until": item.valid_until,
        "confidence": item.confidence,
        "prediction_horizon_seconds": item.prediction_horizon_seconds,
    }


def _receipt_bytes(
    *,
    generated_at: str,
    policy: JeevesFreshnessPolicy,
    records: Iterable[JeevesEvidenceRecord],
) -> bytes:
    payload = {
        "schema": "skeleton.jeeves.evidence-response.v1",
        "generated_at": generated_at,
        "freshness_policy": {
            "max_age_seconds": policy.max_age_seconds,
            "max_future_skew_seconds": policy.max_future_skew_seconds,
        },
        "records": [_record_payload(item) for item in records],
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class JeevesEvidenceAuthority:
    """Deterministic eligibility and receipt authority for Jeeves responses."""

    def __init__(self, policy: JeevesFreshnessPolicy) -> None:
        if not isinstance(policy, JeevesFreshnessPolicy):
            raise TypeError("policy must be JeevesFreshnessPolicy")
        self.policy = policy

    def assemble(
        self,
        records: Iterable[JeevesEvidenceRecord],
        *,
        now: datetime,
    ) -> JeevesEvidenceResponse:
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise JeevesEvidenceError("now must be a timezone-aware datetime")
        now_utc = now.astimezone(timezone.utc)
        materialized = tuple(records)
        if not materialized:
            raise JeevesEvidenceError("response requires evidence")
        if len(materialized) > _MAX_EVIDENCE_RECORDS:
            raise JeevesEvidenceError("response exceeds evidence record bound")

        by_id: dict[str, JeevesEvidenceRecord] = {}
        for record in materialized:
            if not isinstance(record, JeevesEvidenceRecord):
                raise TypeError("records must contain JeevesEvidenceRecord")
            if record.evidence_id in by_id:
                raise JeevesEvidenceError(f"duplicate evidence identity: {record.evidence_id}")
            by_id[record.evidence_id] = record

        for record in materialized:
            if record.kind is JeevesEvidenceKind.MARKET_FACT:
                self._validate_market_fact(record, now_utc)
            for dependency in record.depends_on:
                if dependency not in by_id:
                    raise JeevesEvidenceError(
                        f"{record.evidence_id} references unknown dependency {dependency}"
                    )

        self._validate_graph(by_id)

        facts = tuple(sorted(
            (item for item in materialized if item.kind is JeevesEvidenceKind.MARKET_FACT),
            key=lambda item: item.evidence_id,
        ))
        analyses = tuple(sorted(
            (item for item in materialized if item.kind is JeevesEvidenceKind.ANALYSIS),
            key=lambda item: item.evidence_id,
        ))
        predictions = tuple(sorted(
            (item for item in materialized if item.kind is JeevesEvidenceKind.PREDICTION),
            key=lambda item: item.evidence_id,
        ))
        if (analyses or predictions) and not facts:
            raise JeevesEvidenceError("derived Jeeves output requires factual market lineage")

        generated_at = _canonical_timestamp(now_utc)
        ordered = facts + analyses + predictions
        receipt = sha256(
            _receipt_bytes(generated_at=generated_at, policy=self.policy, records=ordered)
        ).hexdigest()
        return JeevesEvidenceResponse(
            generated_at=generated_at,
            facts=facts,
            analyses=analyses,
            predictions=predictions,
            receipt_digest=receipt,
        )

    def verify(self, response: JeevesEvidenceResponse) -> None:
        if not isinstance(response, JeevesEvidenceResponse):
            raise TypeError("response must be JeevesEvidenceResponse")
        _require_digest(response.receipt_digest, field="receipt_digest")
        generated_at = _parse_timestamp(response.generated_at, field="generated_at")
        rebuilt = self.assemble(response.records(), now=generated_at)
        if rebuilt != response:
            raise JeevesEvidenceError(
                "response receipt does not bind canonical grouping, ordering, and evidence"
            )

    def _validate_market_fact(self, record: JeevesEvidenceRecord, now: datetime) -> None:
        observed = _parse_timestamp(record.observed_at or "", field="observed_at")
        age = (now - observed).total_seconds()
        if age < -self.policy.max_future_skew_seconds:
            raise JeevesEvidenceError(
                f"market fact {record.evidence_id} exceeds allowed future clock skew"
            )
        if age > self.policy.max_age_seconds:
            raise JeevesEvidenceError(f"market fact {record.evidence_id} is stale")
        if record.valid_until is not None:
            valid_until = _parse_timestamp(record.valid_until, field="valid_until")
            if valid_until < observed:
                raise JeevesEvidenceError(
                    f"market fact {record.evidence_id} expires before observation"
                )
            if now > valid_until:
                raise JeevesEvidenceError(f"market fact {record.evidence_id} has expired")

    @staticmethod
    def _validate_graph(records: Mapping[str, JeevesEvidenceRecord]) -> None:
        state: dict[str, int] = {}
        grounded_cache: dict[str, bool] = {}

        def visit(evidence_id: str) -> bool:
            phase = state.get(evidence_id, 0)
            if phase == 1:
                raise JeevesEvidenceError(f"evidence dependency cycle at {evidence_id}")
            if phase == 2:
                return grounded_cache[evidence_id]

            state[evidence_id] = 1
            record = records[evidence_id]
            if record.kind is JeevesEvidenceKind.MARKET_FACT:
                grounded = True
            else:
                grounded = False
                for dependency in record.depends_on:
                    target = records[dependency]
                    if (
                        record.kind is JeevesEvidenceKind.ANALYSIS
                        and target.kind is JeevesEvidenceKind.PREDICTION
                    ):
                        raise JeevesEvidenceError(
                            "analysis cannot use prediction output as factual support"
                        )
                    grounded = visit(dependency) or grounded
                if not grounded:
                    raise JeevesEvidenceError(
                        f"derived evidence {evidence_id} has no factual market lineage"
                    )
            state[evidence_id] = 2
            grounded_cache[evidence_id] = grounded
            return grounded

        for evidence_id in sorted(records):
            visit(evidence_id)


__all__ = [
    "JeevesEvidenceAuthority",
    "JeevesEvidenceError",
    "JeevesEvidenceKind",
    "JeevesEvidenceRecord",
    "JeevesEvidenceResponse",
    "JeevesFreshnessPolicy",
]
