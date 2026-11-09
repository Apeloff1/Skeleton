"""Candidate selection and proof-to-test handoff for VOL-200.

This module extends the bounded VOL-081 formal-method plane without claiming
universal correctness. It answers three narrower engineering questions:

* which implementation risks justify formal-method cost;
* which exact model/bindings/assumptions a checked property refers to; and
* which executable implementation tests inherit that formal evidence.

All identities are deterministic and content-addressed. Formal evidence remains
scoped to the declared model and assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Iterable

FORMAL_CANDIDATE_SCHEMA = "skeleton.contracts.formal-candidates.v1"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_CANDIDATES = 256
_MAX_TEST_TARGETS = 256
_MAX_ASSUMPTIONS = 256
_PROOF_STATUSES = {
    "proved_within_model",
    "refuted",
    "inconclusive_bound",
}


class FormalCandidateError(ValueError):
    """Candidate-selection or proof-handoff contract failed."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise FormalCandidateError(f"{field} must be text")
    if value != value.strip() or not value or not _TOKEN_RE.fullmatch(value):
        raise FormalCandidateError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise FormalCandidateError(f"{field} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > 8192:
        raise FormalCandidateError(f"{field} must be non-empty bounded text")
    return normalized


def _rank(value: object, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int):
        raise FormalCandidateError(f"{field} must be an integer")
    if not minimum <= value <= 5:
        raise FormalCandidateError(f"{field} must be within [{minimum}, 5]")
    return value


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise FormalCandidateError(f"{field} must be an integer within [1, {maximum}]")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FormalCandidateError(f"{field} must be lowercase sha256")
    return value


def _canonical_tuple(
    values: object,
    field: str,
    *,
    sha_values: bool = False,
    maximum: int,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise FormalCandidateError(f"{field} must be a non-empty tuple")
    if len(values) > maximum:
        raise FormalCandidateError(f"{field} exceeds {maximum}")
    normalized = tuple(
        _sha(value, field) if sha_values else _token(value, field)
        for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise FormalCandidateError(f"{field} must contain unique values")
    return tuple(sorted(normalized))


def _digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FormalCandidateError("payload must be deterministic JSON") from exc
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class FormalCandidate:
    """One implementation risk proposed for bounded formal analysis."""

    candidate_id: str
    spec_id: str
    title: str
    consequence_rank: int
    ambiguity_rank: int
    concurrency_ambiguity: int
    authority_ambiguity: int
    recovery_ambiguity: int
    estimated_cost_rank: int
    implementation_test_targets: tuple[str, ...]
    assumption_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _token(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "spec_id", _token(self.spec_id, "spec_id"))
        object.__setattr__(self, "title", _text(self.title, "title"))
        object.__setattr__(
            self,
            "consequence_rank",
            _rank(self.consequence_rank, "consequence_rank"),
        )
        object.__setattr__(
            self,
            "ambiguity_rank",
            _rank(self.ambiguity_rank, "ambiguity_rank"),
        )
        for field in (
            "concurrency_ambiguity",
            "authority_ambiguity",
            "recovery_ambiguity",
        ):
            object.__setattr__(self, field, _rank(getattr(self, field), field, allow_zero=True))
        object.__setattr__(
            self,
            "estimated_cost_rank",
            _rank(self.estimated_cost_rank, "estimated_cost_rank"),
        )
        if (
            self.concurrency_ambiguity
            + self.authority_ambiguity
            + self.recovery_ambiguity
            == 0
        ):
            raise FormalCandidateError(
                "candidate must expose concurrency, authority, or recovery ambiguity"
            )
        object.__setattr__(
            self,
            "implementation_test_targets",
            _canonical_tuple(
                self.implementation_test_targets,
                "implementation_test_targets",
                maximum=_MAX_TEST_TARGETS,
            ),
        )
        object.__setattr__(
            self,
            "assumption_ids",
            _canonical_tuple(
                self.assumption_ids,
                "assumption_ids",
                maximum=_MAX_ASSUMPTIONS,
            ),
        )

    @property
    def boundary_ambiguity(self) -> int:
        return (
            self.concurrency_ambiguity
            + self.authority_ambiguity
            + self.recovery_ambiguity
        )

    @property
    def selection_score(self) -> int:
        """Consequence × ambiguity, plus boundary ambiguity, minus formal cost."""
        return (
            self.consequence_rank * self.ambiguity_rank
            + 2 * self.boundary_ambiguity
            - self.estimated_cost_rank
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_CANDIDATE_SCHEMA,
                "kind": "candidate",
                "candidate_id": self.candidate_id,
                "spec_id": self.spec_id,
                "title": self.title,
                "consequence_rank": self.consequence_rank,
                "ambiguity_rank": self.ambiguity_rank,
                "concurrency_ambiguity": self.concurrency_ambiguity,
                "authority_ambiguity": self.authority_ambiguity,
                "recovery_ambiguity": self.recovery_ambiguity,
                "estimated_cost_rank": self.estimated_cost_rank,
                "implementation_test_targets": list(self.implementation_test_targets),
                "assumption_ids": list(self.assumption_ids),
            }
        )


def rank_formal_candidates(
    candidates: Iterable[FormalCandidate],
    *,
    minimum_score: int = 10,
    maximum_selected: int = 16,
) -> tuple[FormalCandidate, ...]:
    """Return a deterministic, bounded high-value candidate set."""
    if isinstance(minimum_score, bool) or not isinstance(minimum_score, int):
        raise FormalCandidateError("minimum_score must be an integer")
    _positive_int(maximum_selected, "maximum_selected", maximum=_MAX_CANDIDATES)
    items = tuple(candidates)
    if len(items) > _MAX_CANDIDATES:
        raise FormalCandidateError(f"candidate set exceeds {_MAX_CANDIDATES}")
    if any(not isinstance(item, FormalCandidate) for item in items):
        raise FormalCandidateError("candidate set must contain FormalCandidate values")
    ids = [item.candidate_id for item in items]
    if len(ids) != len(set(ids)):
        raise FormalCandidateError("candidate identities must be unique")
    eligible = [item for item in items if item.selection_score >= minimum_score]
    eligible.sort(
        key=lambda item: (
            -item.selection_score,
            -item.consequence_rank,
            -item.ambiguity_rank,
            -item.boundary_ambiguity,
            item.candidate_id,
        )
    )
    return tuple(eligible[:maximum_selected])


@dataclass(frozen=True, slots=True)
class FormalModelRef:
    """Content-bound reference to the exact finite model and assumptions."""

    candidate_id: str
    spec_id: str
    specification_digest: str
    implementation_binding_digests: tuple[str, ...]
    assumption_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _token(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "spec_id", _token(self.spec_id, "spec_id"))
        object.__setattr__(
            self,
            "specification_digest",
            _sha(self.specification_digest, "specification_digest"),
        )
        object.__setattr__(
            self,
            "implementation_binding_digests",
            _canonical_tuple(
                self.implementation_binding_digests,
                "implementation_binding_digests",
                sha_values=True,
                maximum=_MAX_ASSUMPTIONS,
            ),
        )
        object.__setattr__(
            self,
            "assumption_digests",
            _canonical_tuple(
                self.assumption_digests,
                "assumption_digests",
                sha_values=True,
                maximum=_MAX_ASSUMPTIONS,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_CANDIDATE_SCHEMA,
                "kind": "model-ref",
                "candidate_id": self.candidate_id,
                "spec_id": self.spec_id,
                "specification_digest": self.specification_digest,
                "implementation_binding_digests": list(
                    self.implementation_binding_digests
                ),
                "assumption_digests": list(self.assumption_digests),
            }
        )


@dataclass(frozen=True, slots=True)
class VerifiedProperty:
    """Checked property explicitly handed to executable implementation tests."""

    property_id: str
    candidate_id: str
    model_ref_digest: str
    proof_result_digest: str
    proof_status: str
    assumption_digests: tuple[str, ...]
    implementation_test_targets: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "property_id", _token(self.property_id, "property_id"))
        object.__setattr__(self, "candidate_id", _token(self.candidate_id, "candidate_id"))
        object.__setattr__(
            self,
            "model_ref_digest",
            _sha(self.model_ref_digest, "model_ref_digest"),
        )
        object.__setattr__(
            self,
            "proof_result_digest",
            _sha(self.proof_result_digest, "proof_result_digest"),
        )
        if self.proof_status not in _PROOF_STATUSES:
            raise FormalCandidateError("proof_status is not a scoped formal result")
        object.__setattr__(
            self,
            "assumption_digests",
            _canonical_tuple(
                self.assumption_digests,
                "assumption_digests",
                sha_values=True,
                maximum=_MAX_ASSUMPTIONS,
            ),
        )
        object.__setattr__(
            self,
            "implementation_test_targets",
            _canonical_tuple(
                self.implementation_test_targets,
                "implementation_test_targets",
                maximum=_MAX_TEST_TARGETS,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_CANDIDATE_SCHEMA,
                "kind": "verified-property",
                "property_id": self.property_id,
                "candidate_id": self.candidate_id,
                "model_ref_digest": self.model_ref_digest,
                "proof_result_digest": self.proof_result_digest,
                "proof_status": self.proof_status,
                "assumption_digests": list(self.assumption_digests),
                "implementation_test_targets": list(
                    self.implementation_test_targets
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ProofToTestHandoff:
    """Fail-closed bridge from bounded formal evidence to runtime regressions."""

    model_ref: FormalModelRef
    properties: tuple[VerifiedProperty, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.model_ref, FormalModelRef):
            raise FormalCandidateError("model_ref must be FormalModelRef")
        if not isinstance(self.properties, tuple) or not self.properties:
            raise FormalCandidateError("properties must be a non-empty tuple")
        if any(not isinstance(item, VerifiedProperty) for item in self.properties):
            raise FormalCandidateError("properties must contain VerifiedProperty values")
        ids = [item.property_id for item in self.properties]
        if len(ids) != len(set(ids)):
            raise FormalCandidateError("property identities must be unique")
        for item in self.properties:
            if item.candidate_id != self.model_ref.candidate_id:
                raise FormalCandidateError("property candidate does not match model")
            if item.model_ref_digest != self.model_ref.digest:
                raise FormalCandidateError("property references stale/different model")
            if item.assumption_digests != self.model_ref.assumption_digests:
                raise FormalCandidateError(
                    "property assumptions must exactly match model assumptions"
                )
        object.__setattr__(
            self,
            "properties",
            tuple(sorted(self.properties, key=lambda item: item.property_id)),
        )

    @property
    def implementation_test_targets(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    target
                    for item in self.properties
                    for target in item.implementation_test_targets
                }
            )
        )

    def verify_test_inventory(self, available_tests: Iterable[str]) -> None:
        inventory = {_token(item, "available test target") for item in available_tests}
        missing = sorted(set(self.implementation_test_targets) - inventory)
        if missing:
            raise FormalCandidateError(
                "formal proof handoff references unavailable implementation tests: "
                + ",".join(missing)
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_CANDIDATE_SCHEMA,
                "kind": "proof-to-test-handoff",
                "model_ref_digest": self.model_ref.digest,
                "property_digests": [item.digest for item in self.properties],
                "implementation_test_targets": list(self.implementation_test_targets),
            }
        )


__all__ = [
    "FORMAL_CANDIDATE_SCHEMA",
    "FormalCandidate",
    "FormalCandidateError",
    "FormalModelRef",
    "ProofToTestHandoff",
    "VerifiedProperty",
    "rank_formal_candidates",
]
