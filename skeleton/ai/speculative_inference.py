from dataclasses import dataclass
import math


@dataclass(frozen=True)
class DraftToken:
    token: int
    probability: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.token, bool)
            or not isinstance(self.token, int)
            or isinstance(self.probability, bool)
            or not isinstance(self.probability, (int, float))
            or not math.isfinite(self.probability)
            or not 0 <= self.probability <= 1
        ):
            raise ValueError("invalid draft token")


@dataclass(frozen=True)
class SpeculativePlan:
    draft_model: str
    target_model: str
    max_tokens: int
    fallback: bool = True

    def __post_init__(self) -> None:
        if (
            not self.draft_model
            or not self.target_model
            or self.draft_model == self.target_model
            or isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens <= 0
            or not isinstance(self.fallback, bool)
        ):
            raise ValueError("invalid speculative plan")


@dataclass(frozen=True)
class VerificationStep:
    token: DraftToken
    target_token: int
    accepted: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.token, DraftToken)
            or isinstance(self.target_token, bool)
            or not isinstance(self.target_token, int)
            or not isinstance(self.accepted, bool)
        ):
            raise ValueError("invalid verification step")


def verify(plan: SpeculativePlan, drafts, target_tokens) -> tuple[VerificationStep, ...]:
    if not isinstance(plan, SpeculativePlan):
        raise ValueError("speculative plan required")
    draft_items = tuple(drafts)[: plan.max_tokens]
    targets = tuple(target_tokens)
    if any(not isinstance(item, DraftToken) for item in draft_items):
        raise ValueError("draft tokens required")
    if any(isinstance(token, bool) or not isinstance(token, int) for token in targets):
        raise ValueError("integer target tokens required")
    if len(targets) < len(draft_items):
        raise ValueError("target verification incomplete")

    result: list[VerificationStep] = []
    for draft, target in zip(draft_items, targets):
        accepted = draft.token == target
        result.append(VerificationStep(draft, target, accepted))
        if not accepted:
            break
    return tuple(result)


def accepted_tokens(steps) -> tuple[int, ...]:
    items = tuple(steps)
    if any(not isinstance(step, VerificationStep) for step in items):
        raise ValueError("verification steps required")
    return tuple(step.token.token for step in items if step.accepted)


def fallback_required(plan: SpeculativePlan, steps, drafts) -> bool:
    if not isinstance(plan, SpeculativePlan):
        raise ValueError("speculative plan required")
    step_items = tuple(steps)
    draft_items = tuple(drafts)
    if any(not isinstance(step, VerificationStep) for step in step_items):
        raise ValueError("verification steps required")
    attempted = min(len(draft_items), plan.max_tokens)
    return plan.fallback and (
        len(step_items) < attempted or any(not step.accepted for step in step_items)
    )
