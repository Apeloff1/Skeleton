"""Small speculative-decoding primitives.

This layer does not assume a particular model implementation. A draft model
proposes tokens; a verifier accepts the longest prefix it can validate. The
contract is intentionally synchronous and deterministic so it can wrap the
existing TinyTransformer without changing its internals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SpeculationResult:
    accepted: tuple[T, ...]
    rejected: tuple[T, ...]
    proposed: int
    accepted_count: int

    @property
    def acceptance_rate(self) -> float:
        return self.accepted_count / self.proposed if self.proposed else 1.0


class SpeculativeDecoder:
    """Draft/verify coordinator with bounded proposal batches."""

    def __init__(self, max_proposals: int = 8) -> None:
        if max_proposals < 1:
            raise ValueError("max_proposals must be positive")
        self.max_proposals = int(max_proposals)

    def decode(
        self,
        draft: Callable[[Sequence[T], int], Iterable[T]],
        verify: Callable[[Sequence[T], T], bool],
        prefix: Sequence[T],
        *,
        steps: int | None = None,
    ) -> SpeculationResult:
        n = self.max_proposals if steps is None else max(0, min(self.max_proposals, int(steps)))
        proposals = tuple(draft(prefix, n))[:n]
        accepted: list[T] = []
        rejected: list[T] = []
        context = list(prefix)
        for token in proposals:
            if verify(tuple(context), token):
                accepted.append(token)
                context.append(token)
            else:
                rejected.append(token)
                break
        if len(accepted) < len(proposals):
            rejected.extend(proposals[len(accepted) + len(rejected):])
        return SpeculationResult(tuple(accepted), tuple(rejected), len(proposals), len(accepted))


__all__ = ["SpeculationResult", "SpeculativeDecoder"]
