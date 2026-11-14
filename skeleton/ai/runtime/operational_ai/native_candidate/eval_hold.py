"""Separate candidate creation from independent native-quality evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import identity, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class IndependentEvaluationHold:
    candidate_sha256: str
    champion_sha256: str
    corpus_sha256: str
    verifier_id: str | None = None
    real_candidate_eval_sha256: str | None = None
    real_champion_eval_sha256: str | None = None
    human_reviewed: bool = False

    def __post_init__(self) -> None:
        for key in ("candidate_sha256", "champion_sha256", "corpus_sha256"):
            sha(getattr(self, key), key)
        for key in ("real_candidate_eval_sha256", "real_champion_eval_sha256"):
            value = getattr(self, key)
            if value is not None:
                sha(value, key)
        if self.verifier_id is not None:
            identity(self.verifier_id, "verifier")
        if type(self.human_reviewed) is not bool:
            deny("eval-review")

    def record(self) -> dict:
        return {
            "candidate_sha256": self.candidate_sha256,
            "champion_sha256": self.champion_sha256,
            "corpus_sha256": self.corpus_sha256,
            "verifier": self.verifier_id,
            "candidate_evidence": self.real_candidate_eval_sha256,
            "champion_evidence": self.real_champion_eval_sha256,
            "human_reviewed": self.human_reviewed,
            "review_evidence_present": bool(
                self.verifier_id and self.real_candidate_eval_sha256
                and self.real_champion_eval_sha256 and self.human_reviewed
            ),
            # Even complete candidate evidence does not authorize release.
            "promotion_authorized": False,
            "release_certified": False,
        }
