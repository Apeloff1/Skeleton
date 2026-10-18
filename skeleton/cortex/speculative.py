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


def _make_cache(model, *, use_cache: bool = True):
    if not use_cache or getattr(model, "use_mod", False):
        return None
    if not hasattr(model, "_logits_window") or not hasattr(model, "n_layers") or not hasattr(model, "ctx"):
        return None
    from skeleton.cortex.transformer import KVCache
    return KVCache(int(model.n_layers), int(model.ctx))


def _greedy_token(model, ids: Sequence[int], cache=None) -> int:
    """Highest-logit next id. Ties break toward the lower id."""
    if not ids:
        raise ValueError("speculative context must be non-empty")
    window = [int(token) for token in ids][-int(model.ctx):]
    if cache is not None and hasattr(model, "_logits_window"):
        logits = list(model._logits_window(window, cache))
    else:
        logits = list(model._logits(window))
    if not logits:
        raise ValueError("speculative model returned no logits")
    return max(range(len(logits)), key=lambda index: (logits[index], -index))


def greedy_speculative(
    verifier,
    draft,
    prefix: Sequence[int],
    n: int,
    *,
    proposals: int = 4,
    use_cache: bool = True,
) -> tuple[tuple[int, ...], SpeculationResult]:
    """Publish the verifier's greedy continuation, using the draft as a proposal.

    A draft token is kept only when it is also the verifier's next greedy id.
    On rejection the verifier's own id is published instead. The returned ids
    therefore match a verifier-only greedy decode, and the draft cannot change
    the published tokens.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    if isinstance(proposals, bool) or not isinstance(proposals, int) or not 1 <= proposals <= 8:
        raise ValueError("proposals must be in [1, 8]")
    if int(getattr(verifier, "V", -1)) != int(getattr(draft, "V", -2)):
        raise ValueError("speculative mouths must share a vocabulary")
    context = [int(token) for token in prefix]
    if not context:
        raise ValueError("speculative context must be non-empty")
    v_cache = _make_cache(verifier, use_cache=use_cache)
    d_cache = _make_cache(draft, use_cache=use_cache)
    published: list[int] = []
    proposed = 0
    accepted = 0
    rejected: list[int] = []
    while len(published) < n:
        room = n - len(published)
        drafted: list[int] = []
        cursor = list(context)
        for _ in range(min(proposals, room)):
            token = _greedy_token(draft, cursor, d_cache)
            drafted.append(token)
            cursor.append(token)
        proposed += len(drafted)
        kept = 0
        fallback_token: int | None = None
        for token in drafted:
            v_token = _greedy_token(verifier, context, v_cache)
            if v_token != token:
                rejected.append(token)
                fallback_token = v_token
                break
            context.append(token)
            published.append(token)
            kept += 1
        accepted += kept
        if kept < len(drafted):
            rejected.extend(drafted[kept + 1:])
            if len(published) < n and fallback_token is not None:
                context.append(fallback_token)
                published.append(fallback_token)
    result = SpeculationResult(tuple(published), tuple(rejected), proposed, accepted)
    return tuple(published), result


def cooperative_speculative(
    verifiers: Sequence[object],
    draft: object,
    prefix: Sequence[int],
    n: int,
    *,
    proposals: int = 4,
    weights: Sequence[float] | None = None,
) -> tuple[tuple[int, ...], SpeculationResult]:
    """Speculative decode verified against a cooperative probability ensemble of verifiers."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    if isinstance(proposals, bool) or not isinstance(proposals, int) or not 1 <= proposals <= 8:
        raise ValueError("proposals must be in [1, 8]")
    if not verifiers:
        raise ValueError("verifiers must be non-empty")
    vocab = int(getattr(draft, "V", -2))
    for model in verifiers:
        if int(getattr(model, "V", -1)) != vocab:
            raise ValueError("speculative mouths must share a vocabulary")
    context = [int(token) for token in prefix]
    if not context:
        raise ValueError("speculative context must be non-empty")
    from skeleton.cortex.gossip import cooperative_logits

    d_cache = _make_cache(draft, use_cache=True)
    published: list[int] = []
    proposed = 0
    accepted = 0
    rejected: list[int] = []
    while len(published) < n:
        room = n - len(published)
        drafted: list[int] = []
        cursor = list(context)
        for _ in range(min(proposals, room)):
            token = _greedy_token(draft, cursor, d_cache)
            drafted.append(token)
            cursor.append(token)
        proposed += len(drafted)
        kept = 0
        fallback_token: int | None = None
        for token in drafted:
            fused_logits = cooperative_logits(verifiers, context, weights=weights)
            v_token = max(range(len(fused_logits)), key=lambda index: (fused_logits[index], -index))
            if v_token != token:
                rejected.append(token)
                fallback_token = v_token
                break
            context.append(token)
            published.append(token)
            kept += 1
        accepted += kept
        if kept < len(drafted):
            rejected.extend(drafted[kept + 1:])
            if len(published) < n and fallback_token is not None:
                context.append(fallback_token)
                published.append(fallback_token)
    result = SpeculationResult(tuple(published), tuple(rejected), proposed, accepted)
    return tuple(published), result


__all__ = ["SpeculationResult", "SpeculativeDecoder", "cooperative_speculative", "greedy_speculative"]
