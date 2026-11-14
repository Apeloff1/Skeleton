"""Independent benchmark source separation; never train on held-out evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from .dedup import normalized, text_digest
from .records import TrainingExample
from .strict import digest
from .errors import deny


@dataclass(frozen=True, slots=True)
class ContaminationResult:
    checked_items: int
    benchmark_steps: int
    exact_prompt_overlaps: tuple[str, ...]
    exact_pair_overlaps: tuple[str, ...]
    result_sha256: str
    needs_independent_near_duplicate_review: bool = True

    @property
    def exact_clear(self) -> bool:
        return not self.exact_prompt_overlaps and not self.exact_pair_overlaps

    def record(self) -> dict:
        return {
            "checked_items": self.checked_items,
            "benchmark_steps": self.benchmark_steps,
            "exact_prompt_overlaps": list(self.exact_prompt_overlaps),
            "exact_pair_overlaps": list(self.exact_pair_overlaps),
            "result_sha256": self.result_sha256,
            "needs_independent_near_duplicate_review": self.needs_independent_near_duplicate_review,
            "release_qualified": False,
        }


def scan(examples: tuple[TrainingExample, ...]) -> ContaminationResult:
    from ..native_qualification.corpus import iter_cases
    train_prompts = {text_digest(e.prompt): e.item_id for e in examples}
    train_pairs = {
        digest([normalized(e.prompt), normalized(e.completion)]): e.item_id
        for e in examples
    }
    overlap_prompt, overlap_pair = [], []
    steps = 0
    for case in iter_cases():
        for step in case.steps:
            steps += 1
            ph = text_digest(step.prompt)
            if ph in train_prompts:
                overlap_prompt.append(train_prompts[ph])
            for check in step.checks:
                if check.kind == "exact" and type(check.expected) is str:
                    eh = digest([normalized(step.prompt), normalized(check.expected)])
                    if eh in train_pairs:
                        overlap_pair.append(train_pairs[eh])
    overlap_prompt = tuple(sorted(set(overlap_prompt)))
    overlap_pair = tuple(sorted(set(overlap_pair)))
    summary = {"count": len(examples), "benchmark_steps": steps,
               "exact_prompt": overlap_prompt, "exact_pair": overlap_pair}
    return ContaminationResult(
        len(examples), steps, overlap_prompt, overlap_pair, digest(summary)
    )


def require_clear_exact(proof: ContaminationResult) -> None:
    if type(proof) is not ContaminationResult or not proof.exact_clear:
        deny("benchmark-source-contamination")
