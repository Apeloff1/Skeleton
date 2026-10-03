"""Independent-verifier diversity and reward-gaming challenge contract.

Optimization against one reward/verifier can exploit its blind spots. Promotion
therefore requires evidence from independent verifier families plus an explicit
gaming challenge that is not authored by the candidate generator.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence


class VerifierGamingError(RuntimeError):
    """Verifier diversity or anti-gaming evidence is insufficient."""


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
        raise VerifierGamingError("verifier value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerifierGamingError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise VerifierGamingError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise VerifierGamingError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class VerifierDescriptor:
    verifier_id: str
    family_id: str
    implementation_digest: str
    training_root: str | None
    evaluation_root: str
    generator_family_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("verifier_id", "family_id"):
            object.__setattr__(self, field_name, _text(field_name, getattr(self, field_name)))
        object.__setattr__(
            self,
            "implementation_digest",
            _sha("implementation_digest", self.implementation_digest),
        )
        object.__setattr__(
            self, "evaluation_root", _sha("evaluation_root", self.evaluation_root)
        )
        if self.training_root is not None:
            object.__setattr__(
                self, "training_root", _sha("training_root", self.training_root)
            )
        if self.generator_family_id is not None:
            object.__setattr__(
                self,
                "generator_family_id",
                _text("generator_family_id", self.generator_family_id),
            )

    @property
    def identity(self) -> str:
        return "verifier:" + _digest(
            {
                "verifier_id": self.verifier_id,
                "family_id": self.family_id,
                "implementation_digest": self.implementation_digest,
                "training_root": self.training_root,
                "evaluation_root": self.evaluation_root,
                "generator_family_id": self.generator_family_id,
            }
        )


@dataclass(frozen=True, slots=True)
class VerifierJudgement:
    candidate_id: str
    verifier_identity: str
    verifier_family_id: str
    passed: bool
    score: float
    evidence_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(
            self, "verifier_identity", _text("verifier_identity", self.verifier_identity)
        )
        object.__setattr__(
            self, "verifier_family_id", _text("verifier_family_id", self.verifier_family_id)
        )
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise VerifierGamingError("score must be numeric")
        score = float(self.score)
        if not 0.0 <= score <= 1.0:
            raise VerifierGamingError("score must be in [0, 1]")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_id": self.candidate_id,
                "verifier_identity": self.verifier_identity,
                "verifier_family_id": self.verifier_family_id,
                "passed": self.passed,
                "score": self.score,
                "evidence_ref": self.evidence_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class GamingChallenge:
    challenge_id: str
    author_family_id: str
    corpus_digest: str
    target_failure_modes: tuple[str, ...]
    passed: bool
    evidence_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "challenge_id", _text("challenge_id", self.challenge_id))
        object.__setattr__(
            self, "author_family_id", _text("author_family_id", self.author_family_id)
        )
        object.__setattr__(self, "corpus_digest", _sha("corpus_digest", self.corpus_digest))
        modes = tuple(_text("target_failure_mode", item) for item in self.target_failure_modes)
        if not modes:
            raise VerifierGamingError("gaming challenge requires target failure modes")
        if len(modes) != len(set(modes)):
            raise VerifierGamingError("target failure modes must be unique")
        object.__setattr__(self, "target_failure_modes", modes)
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "challenge_id": self.challenge_id,
                "author_family_id": self.author_family_id,
                "corpus_digest": self.corpus_digest,
                "target_failure_modes": list(self.target_failure_modes),
                "passed": self.passed,
                "evidence_ref": self.evidence_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class AntiGamingPromotionReceipt:
    candidate_id: str
    generator_family_id: str
    verifier_families: tuple[str, ...]
    judgement_digests: tuple[str, ...]
    challenge_digest: str
    minimum_score: float

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.anti_gaming_promotion.v1",
                "candidate_id": self.candidate_id,
                "generator_family_id": self.generator_family_id,
                "verifier_families": list(self.verifier_families),
                "judgement_digests": list(self.judgement_digests),
                "challenge_digest": self.challenge_digest,
                "minimum_score": self.minimum_score,
            }
        )


class VerifierGamingGate:
    def __init__(self, *, minimum_verifier_families: int = 2, minimum_score: float = 0.5) -> None:
        if (
            isinstance(minimum_verifier_families, bool)
            or not isinstance(minimum_verifier_families, int)
            or minimum_verifier_families < 2
        ):
            raise VerifierGamingError("minimum_verifier_families must be at least 2")
        if isinstance(minimum_score, bool) or not isinstance(minimum_score, (int, float)):
            raise VerifierGamingError("minimum_score must be numeric")
        score = float(minimum_score)
        if not 0.0 <= score <= 1.0:
            raise VerifierGamingError("minimum_score must be in [0, 1]")
        self.minimum_verifier_families = minimum_verifier_families
        self.minimum_score = score

    def qualify(
        self,
        *,
        candidate_id: str,
        generator_family_id: str,
        verifiers: Sequence[VerifierDescriptor],
        judgements: Sequence[VerifierJudgement],
        gaming_challenge: GamingChallenge,
    ) -> AntiGamingPromotionReceipt:
        candidate = _text("candidate_id", candidate_id)
        generator = _text("generator_family_id", generator_family_id)
        if not isinstance(gaming_challenge, GamingChallenge):
            raise TypeError("gaming_challenge must be GamingChallenge")
        if gaming_challenge.author_family_id == generator:
            raise VerifierGamingError("generator family cannot author its own gaming challenge")
        if not gaming_challenge.passed:
            raise VerifierGamingError("candidate failed adversarial gaming challenge")

        registry: dict[str, VerifierDescriptor] = {}
        for verifier in verifiers:
            if not isinstance(verifier, VerifierDescriptor):
                raise TypeError("verifiers must contain VerifierDescriptor values")
            if verifier.identity in registry:
                raise VerifierGamingError("duplicate verifier identity")
            if verifier.family_id == generator or verifier.generator_family_id == generator:
                raise VerifierGamingError("verifier is not independent from generator family")
            registry[verifier.identity] = verifier

        families = {item.family_id for item in registry.values()}
        if len(families) < self.minimum_verifier_families:
            raise VerifierGamingError("insufficient independent verifier-family diversity")

        seen: set[str] = set()
        judgement_digests: list[str] = []
        judged_families: set[str] = set()
        for judgement in judgements:
            if not isinstance(judgement, VerifierJudgement):
                raise TypeError("judgements must contain VerifierJudgement values")
            if judgement.candidate_id != candidate:
                raise VerifierGamingError("judgement candidate identity mismatch")
            verifier = registry.get(judgement.verifier_identity)
            if verifier is None:
                raise VerifierGamingError("judgement references unknown verifier")
            if judgement.verifier_family_id != verifier.family_id:
                raise VerifierGamingError("judgement verifier-family identity mismatch")
            if judgement.verifier_identity in seen:
                raise VerifierGamingError("duplicate verifier judgement")
            seen.add(judgement.verifier_identity)
            if not judgement.passed or judgement.score < self.minimum_score:
                raise VerifierGamingError("candidate failed independent verifier threshold")
            judged_families.add(verifier.family_id)
            judgement_digests.append(judgement.digest)

        if judged_families != families:
            raise VerifierGamingError("every verifier family must contribute passing evidence")

        return AntiGamingPromotionReceipt(
            candidate_id=candidate,
            generator_family_id=generator,
            verifier_families=tuple(sorted(families)),
            judgement_digests=tuple(sorted(judgement_digests)),
            challenge_digest=gaming_challenge.digest,
            minimum_score=self.minimum_score,
        )


__all__ = [
    "AntiGamingPromotionReceipt",
    "GamingChallenge",
    "VerifierDescriptor",
    "VerifierGamingError",
    "VerifierGamingGate",
    "VerifierJudgement",
]
