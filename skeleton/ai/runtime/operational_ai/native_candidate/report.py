"""Conservative source and training report composition, never a grade claim."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import digest, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class NativeCandidateReport:
    source_sha256: str
    rights_sha256: str
    split_sha256: str
    tokenizer_sha256: str
    champion_sha256: str
    candidate_sha256: str | None
    actual_steps: int | None
    source_complete: bool
    exact_overlap_clear: bool
    native_gradient_complete: bool
    independent_eval_complete: bool = False
    human_review_complete: bool = False

    def __post_init__(self) -> None:
        for name in ("source_sha256", "rights_sha256", "split_sha256",
                     "tokenizer_sha256", "champion_sha256"):
            sha(getattr(self, name), name)
        if self.candidate_sha256 is not None:
            sha(self.candidate_sha256, "candidate")
        if self.actual_steps is not None:
            from .strict import number
            number(self.actual_steps, "steps", 1, 1000000)
        for name in ("source_complete", "exact_overlap_clear",
                     "native_gradient_complete", "independent_eval_complete",
                     "human_review_complete"):
            if type(getattr(self, name)) is not bool:
                deny("report-boolean")

    def record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.report.v1",
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
            "candidate_only": True,
            "eligible_for_independent_review": (
                self.source_complete and self.exact_overlap_clear
                and self.native_gradient_complete
                and self.candidate_sha256 is not None and self.actual_steps is not None
            ),
            "near_duplicate_review_complete": False,
            "automatic_promotion": False,
            "merge_certified": False,
            "release_certified": False,
        }

    @property
    def digest(self) -> str:
        return digest(self.record())
