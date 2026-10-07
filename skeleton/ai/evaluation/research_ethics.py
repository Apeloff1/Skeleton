from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchRisk:
    human_subjects: bool
    sensitive_data: bool
    dual_use: bool

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (self.human_subjects, self.sensitive_data, self.dual_use)
        ):
            raise ValueError("research risk assertions must be boolean")

    @property
    def sensitive(self) -> bool:
        return self.human_subjects or self.sensitive_data or self.dual_use


@dataclass(frozen=True)
class EthicsReview:
    review_id: str
    risk: ResearchRisk
    consent: bool
    oversight_id: str | None

    def __post_init__(self) -> None:
        if not self.review_id or not isinstance(self.risk, ResearchRisk):
            raise ValueError("review identity and risk required")
        if not isinstance(self.consent, bool):
            raise ValueError("consent assertion must be boolean")
        if self.oversight_id is not None and not self.oversight_id:
            raise ValueError("oversight_id cannot be empty")


@dataclass(frozen=True)
class EthicsDecision:
    approved: bool
    reason: str


def decide(review: EthicsReview) -> EthicsDecision:
    if not isinstance(review, EthicsReview):
        return EthicsDecision(False, "invalid review")
    if review.risk.sensitive and (not review.consent or not review.oversight_id):
        return EthicsDecision(False, "consent and oversight required")
    return EthicsDecision(True, "review criteria satisfied")
