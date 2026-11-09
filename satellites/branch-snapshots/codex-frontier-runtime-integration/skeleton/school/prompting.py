"""Prompt-refinement policy for Jeeves school interactions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class RefinementNeed(str, Enum):
    NONE = "none"
    SCOPE = "scope"
    INPUTS = "inputs"
    OUTPUTS = "outputs"
    CONSTRAINTS = "constraints"
    SUCCESS = "success_criteria"


@dataclass(frozen=True)
class PromptRefinement:
    original: str
    needs: tuple[RefinementNeed, ...]
    questions: tuple[str, ...]
    normalized_goal: str


def refine_prompt(prompt: str) -> PromptRefinement:
    """Identify ambiguity before Jeeves commits to a solution."""
    original = prompt.strip()
    if not original:
        raise ValueError("prompt must be non-empty")
    lower = original.lower()
    needs: list[RefinementNeed] = []
    questions: list[str] = []
    if len(original.split()) < 5:
        needs.append(RefinementNeed.SCOPE)
        questions.append("What exact outcome should we produce?")
    if not re.search(r"\b(input|given|from|using|receive)\b", lower):
        needs.append(RefinementNeed.INPUTS)
        questions.append("What inputs, examples, or starting material do we have?")
    if not re.search(r"\b(output|return|produce|result|show)\b", lower):
        needs.append(RefinementNeed.OUTPUTS)
        questions.append("What should the finished result look like?")
    if not re.search(r"\b(must|should|only|without|limit|constraint)\b", lower):
        needs.append(RefinementNeed.CONSTRAINTS)
        questions.append("Are there constraints, required tools, or boundaries I should respect?")
    if not re.search(r"\b(test|success|correct|done|works|accept)\b", lower):
        needs.append(RefinementNeed.SUCCESS)
        questions.append("How will we know the result is correct or successful?")
    return PromptRefinement(original, tuple(needs), tuple(questions[:4]), original)
