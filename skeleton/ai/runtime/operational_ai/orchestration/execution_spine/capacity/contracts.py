"""Immutable contracts for capacity planning without lossy authority writes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..contracts import SpineError, SpineLimits, Identity
from ..context import Projection


@dataclass(frozen=True, slots=True)
class CapacityPolicy:
    """Controls resource consumption during one pre-inference planning pass.

    The source cap guards against unbounded search iterables. The planner never
    truncates a source's content; it either admits the entire trusted-by-custody
    excerpt as untrusted inference data, or omits it and records the omission.
    """
    max_source_candidates: int = 128
    maximum_trials: int = 8192
    require_native_precount: bool = False

    def __post_init__(self) -> None:
        if type(self.max_source_candidates) is not int or not 1 <= self.max_source_candidates <= 128:
            raise SpineError('invalid candidate evidence ceiling')
        if type(self.maximum_trials) is not int or not 1 <= self.maximum_trials <= 8192:
            raise SpineError('invalid context trial bound')
        if type(self.require_native_precount) is not bool:
            raise SpineError('invalid native tokenizer policy')


@dataclass(frozen=True, slots=True)
class CapacityPlan:
    """A compiled native context and its deliberately limited admission proof."""
    projection: Projection
    history_digest: str
    evidence_digest: str
    selected_evidence_digest: str
    retained_turns: int
    omitted_turns: int
    evidence_candidates: int
    retained_sources: int
    omitted_sources: int
    trials: int
    token_status: str
    tokens: int | None
    conservative_estimate: int
    proof_digest: str
    source_identities: tuple[tuple[str, int, str], ...]

    def __post_init__(self) -> None:
        from ..contracts import hexdigest
        if not isinstance(self.projection, Projection):
            raise SpineError('capacity projection required')
        for name in ('history_digest', 'evidence_digest', 'selected_evidence_digest', 'proof_digest'):
            hexdigest(getattr(self, name), name)
        for name in ('retained_turns', 'omitted_turns', 'evidence_candidates',
                     'retained_sources', 'omitted_sources', 'trials', 'conservative_estimate'):
            val = getattr(self, name)
            if type(val) is not int or val < 0:
                raise SpineError('invalid context loss accounting')
        if self.omitted_sources + self.retained_sources != self.evidence_candidates:
            raise SpineError('evidence loss accounting mismatch')
        if self.token_status not in ('exact-backend-count-admitted', 'native-backend-must-enforce-unknown-precount'):
            raise SpineError('unrecognized token admission status')
        if self.tokens is not None and (type(self.tokens) is not int or self.tokens < 0):
            raise SpineError('invalid native pre-count')

    @property
    def messages(self) -> tuple[dict, ...]:
        return self.projection.messages

    @property
    def sources(self) -> tuple[dict, ...]:
        return self.projection.sources
