"""P1 terminal failure-journey qualification.

PROM-02 is a non-authoritative exact-head verifier. It proves that every
mandatory P1 failure family and terminal journey class has independent passing
evidence on one commit. It cannot mutate maturity or sign production promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_evidence import P1TerminalEvidenceDecision


P1_FAILURE_JOURNEY_SCHEMA_VERSION = 1
P1_FAILURE_JOURNEY_TASK_ID = "P1-PROM-02"
P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID = "ACC-P1-PROM-02"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


class P1FailureJourneyError(ValueError):
    """Terminal failure-journey evidence is malformed."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P1FailureJourneyError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise P1FailureJourneyError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise P1FailureJourneyError(f"{field} must be lowercase git sha")
    return value


def _sha64(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA64_RE.fullmatch(value):
        raise P1FailureJourneyError(f"{field} must be lowercase sha256")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise P1FailureJourneyError(
            "failure-journey payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise P1FailureJourneyError(
            "evidence_refs must contain EvidenceRef values"
        )
    rows: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise P1FailureJourneyError(
                "evidence_refs must contain EvidenceRef values"
            )
        rows[(item.source, item.digest, item.category)] = item
    if not rows:
        raise P1FailureJourneyError("evidence_refs must be non-empty")
    return tuple(rows[key] for key in sorted(rows))


@dataclass(frozen=True, slots=True)
class FailureJourneyObservation:
    family: str
    repository: str
    commit_sha: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    passed: bool
    independent: bool
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", _text(self.family, "family", maximum=128))
        object.__setattr__(
            self,
            "repository",
            _text(self.repository, "repository", maximum=256),
        )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id", maximum=256),
        )
        object.__setattr__(
            self,
            "verifier_digest",
            _sha64(self.verifier_digest, "verifier_digest"),
        )
        object.__setattr__(
            self,
            "test_manifest_digest",
            _sha64(self.test_manifest_digest, "test_manifest_digest"),
        )
        if not isinstance(self.passed, bool):
            raise P1FailureJourneyError("passed must be boolean")
        if not isinstance(self.independent, bool):
            raise P1FailureJourneyError("independent must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
            "passed": self.passed,
            "independent": self.independent,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class P1FailureJourneyDecision:
    accepted: bool
    reasons: tuple[str, ...]
    repository: str
    commit_sha: str
    prom01_bundle_digest: str
    prom01_promotion_ready: bool
    required_families: tuple[str, ...]
    required_journey_classes: tuple[str, ...]
    observation_digests: tuple[str, ...]
    task_id: str = P1_FAILURE_JOURNEY_TASK_ID
    accountability_id: str = P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID
    schema_version: int = P1_FAILURE_JOURNEY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise P1FailureJourneyError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise P1FailureJourneyError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "repository",
            _text(self.repository, "repository", maximum=256),
        )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        object.__setattr__(
            self,
            "prom01_bundle_digest",
            _sha64(self.prom01_bundle_digest, "prom01_bundle_digest"),
        )
        if not isinstance(self.prom01_promotion_ready, bool):
            raise P1FailureJourneyError(
                "prom01_promotion_ready must be boolean"
            )
        for field in ("required_families", "required_journey_classes"):
            values = getattr(self, field)
            if not isinstance(values, tuple) or not values:
                raise P1FailureJourneyError(f"{field} must be non-empty tuple")
            normalized = tuple(sorted({_text(v, field, maximum=128) for v in values}))
            object.__setattr__(self, field, normalized)
        if not isinstance(self.observation_digests, tuple) or not self.observation_digests:
            raise P1FailureJourneyError(
                "observation_digests must be non-empty tuple"
            )
        object.__setattr__(
            self,
            "observation_digests",
            tuple(sorted(_sha64(v, "observation_digest") for v in self.observation_digests)),
        )
        if self.task_id != P1_FAILURE_JOURNEY_TASK_ID:
            raise P1FailureJourneyError("task_id drift")
        if self.accountability_id != P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID:
            raise P1FailureJourneyError("accountability_id drift")
        if self.schema_version != P1_FAILURE_JOURNEY_SCHEMA_VERSION:
            raise P1FailureJourneyError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "prom01_bundle_digest": self.prom01_bundle_digest,
            "prom01_promotion_ready": self.prom01_promotion_ready,
            "required_families": list(self.required_families),
            "required_journey_classes": list(self.required_journey_classes),
            "observation_digests": list(self.observation_digests),
            "promotion_authority": False,
            "signed_promotion": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prom-02:terminal-failure-journeys",
    ) -> EvidenceRef:
        if not self.accepted:
            raise P1FailureJourneyError(
                "rejected failure journeys cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="p1_terminal_failure_journeys",
        )


def qualify_p1_failure_journeys(
    *,
    observations: Iterable[FailureJourneyObservation],
    expected_repository: str,
    expected_head: str,
    required_families: Iterable[str],
    required_journey_classes: Iterable[str],
    journey_class_families: dict[str, Iterable[str]],
    prom01_bundle: P1TerminalEvidenceDecision,
) -> P1FailureJourneyDecision:
    repository = _text(expected_repository, "expected_repository", maximum=256)
    head = _sha40(expected_head, "expected_head")
    if not isinstance(prom01_bundle, P1TerminalEvidenceDecision):
        raise TypeError("prom01_bundle must be P1TerminalEvidenceDecision")
    prom01 = prom01_bundle.decision_digest
    required = tuple(sorted({_text(v, "required_family", maximum=128) for v in required_families}))
    classes = tuple(
        sorted({_text(v, "required_journey_class", maximum=128) for v in required_journey_classes})
    )
    if not required or not classes:
        raise P1FailureJourneyError("required failure coverage cannot be empty")

    class_map: dict[str, tuple[str, ...]] = {}
    for name, families in journey_class_families.items():
        key = _text(name, "journey_class", maximum=128)
        members = tuple(sorted({_text(v, "journey_family", maximum=128) for v in families}))
        if not members:
            raise P1FailureJourneyError(
                f"{key}: journey class must map to at least one family"
            )
        class_map[key] = members

    reasons: list[str] = []
    if not prom01_bundle.accepted:
        reasons.append("prom01-bundle-rejected")
    if prom01_bundle.repository != repository:
        reasons.append("prom01-repository-mismatch")
    if prom01_bundle.commit_sha != head:
        reasons.append("prom01-exact-head-mismatch")

    by_family: dict[str, FailureJourneyObservation] = {}
    unknown: set[str] = set()
    duplicate: set[str] = set()
    for observation in observations:
        if not isinstance(observation, FailureJourneyObservation):
            raise TypeError(
                "observations must contain FailureJourneyObservation"
            )
        if observation.family not in set(required):
            unknown.add(observation.family)
            continue
        if observation.family in by_family:
            duplicate.add(observation.family)
            continue
        by_family[observation.family] = observation

    reasons.extend(f"unknown-family:{item}" for item in sorted(unknown))
    reasons.extend(f"duplicate-family:{item}" for item in sorted(duplicate))
    reasons.extend(
        f"missing-family:{item}"
        for item in sorted(set(required) - set(by_family))
    )

    for family, observation in sorted(by_family.items()):
        if observation.repository != repository:
            reasons.append(f"repository-mismatch:{family}")
        if observation.commit_sha != head:
            reasons.append(f"exact-head-mismatch:{family}")
        if not observation.passed:
            reasons.append(f"journey-failed:{family}")
        if not observation.independent:
            reasons.append(f"journey-not-independent:{family}")

    for journey_class in classes:
        members = class_map.get(journey_class)
        if members is None:
            reasons.append(f"journey-class-unmapped:{journey_class}")
            continue
        unknown_members = sorted(set(members) - set(required))
        if unknown_members:
            reasons.append(
                f"journey-class-unknown-family:{journey_class}:"
                + ",".join(unknown_members)
            )
            continue
        uncovered = sorted(set(members) - set(by_family))
        if uncovered:
            reasons.append(
                f"journey-class-uncovered:{journey_class}:"
                + ",".join(uncovered)
            )

    normalized = tuple(sorted(set(reasons)))
    return P1FailureJourneyDecision(
        accepted=not normalized,
        reasons=normalized,
        repository=repository,
        commit_sha=head,
        prom01_bundle_digest=prom01,
        prom01_promotion_ready=prom01_bundle.promotion_ready,
        required_families=required,
        required_journey_classes=classes,
        observation_digests=tuple(
            observation.observation_digest
            for _, observation in sorted(by_family.items())
        ),
    )


__all__ = [
    "P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID",
    "P1_FAILURE_JOURNEY_SCHEMA_VERSION",
    "P1_FAILURE_JOURNEY_TASK_ID",
    "FailureJourneyObservation",
    "P1FailureJourneyDecision",
    "P1FailureJourneyError",
    "qualify_p1_failure_journeys",
]
