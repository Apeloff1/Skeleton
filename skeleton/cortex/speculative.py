"""Small speculative-decoding primitives.

This layer does not assume a particular model implementation. A draft model
proposes tokens; a verifier accepts the longest prefix it can validate. The
contract is intentionally synchronous and deterministic so it can wrap the
existing TinyTransformer without changing its internals.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import math
from typing import Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")
_MAX_DRAFT_MODELS = 8
_MAX_LOOKAHEAD_TOKENS = 2048
_MAX_PREFIX_TOKENS = 16_384


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
        if type(max_proposals) is not int or not 1 <= max_proposals <= 256:
            raise ValueError("max_proposals must be an integer in [1, 256]")
        self.max_proposals = max_proposals

    def decode(
        self,
        draft: Callable[[Sequence[T], int], Iterable[T]],
        verify: Callable[[Sequence[T], T], bool],
        prefix: Sequence[T],
        *,
        steps: int | None = None,
    ) -> SpeculationResult:
        n = self.max_proposals if steps is None else max(0, min(self.max_proposals, int(steps)))
        # Never exhaust an arbitrary proposal iterable before applying the
        # admission bound: it may be infinite or perform expensive work.
        proposals = tuple(islice(draft(prefix, n), n)) if n else ()
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


class GrammarBudgetLogitProcessor:
    """Neuro-Symbolic Grammar & Hardware-Budget Constrained Logit Masker.

    Applies hard masks (-inf) and soft domain biases to raw token logits during
    generation to enforce:
      - allowed/banned token vocabularies (e.g., GDScript syntax or ROM assembly tokens),
      - soft penalties for repeating n-grams,
      - required keyword urgency boosting as remaining token budget shrinks,
      - hardware tile/sprite/palette token affinity.
    """

    def __init__(
        self,
        itos: Sequence[str],
        *,
        allowed_tokens: Sequence[str] | None = None,
        banned_tokens: Sequence[str] | None = None,
        required_tokens: Sequence[str] | None = None,
        domain_boost_tokens: Sequence[str] | None = None,
        boost_bias: float = 2.25,
        no_repeat_ngram_size: int = 2,
    ) -> None:
        self.itos = tuple(str(t) for t in itos)
        self.stoi = {t: i for i, t in enumerate(self.itos)}
        self.allowed_ids: set[int] | None = (
            {self.stoi[t] for t in allowed_tokens if t in self.stoi}
            if allowed_tokens is not None
            else None
        )
        self.banned_ids: set[int] = {self.stoi[t] for t in (banned_tokens or ()) if t in self.stoi}
        self.required_ids: list[int] = list(dict.fromkeys(
            self.stoi[t] for t in (required_tokens or ()) if t in self.stoi
        ))
        self.boost_ids: set[int] = {self.stoi[t] for t in (domain_boost_tokens or ()) if t in self.stoi}
        self.boost_bias = float(boost_bias)
        if not math.isfinite(self.boost_bias):
            raise ValueError("grammar boost_bias must be finite")
        self.no_repeat_ngram_size = max(0, int(no_repeat_ngram_size))

    def process(
        self,
        logits: Sequence[float],
        generated_ids: Sequence[int],
        *,
        steps_remaining: int = 1,
    ) -> list[float]:
        out = [float(x) for x in logits]
        vocab = len(out)
        if not vocab or vocab != len(self.itos):
            raise ValueError("grammar logits must match the nonempty vocabulary")
        if any(math.isnan(value) or value == math.inf for value in out):
            raise ValueError("grammar logits contain NaN or positive infinity")
        if type(steps_remaining) is not int or steps_remaining < 1:
            raise ValueError("remaining grammar budget must be a positive integer")

        if self.allowed_ids is not None:
            for i in range(vocab):
                if i not in self.allowed_ids:
                    out[i] = -math.inf

        for b_id in self.banned_ids:
            if 0 <= b_id < vocab:
                out[b_id] = -math.inf

        if any(
            token in self.banned_ids or (self.allowed_ids is not None and token not in self.allowed_ids)
            for token in self.required_ids
        ):
            raise ValueError("required grammar tokens conflict with allowed or banned tokens")

        # Block repeating n-grams
        n = self.no_repeat_ngram_size
        if n >= 2 and len(generated_ids) >= n - 1:
            prefix_tail = tuple(generated_ids[-(n - 1):])
            blocked: set[int] = set()
            for idx in range(len(generated_ids) - n + 1):
                if tuple(generated_ids[idx:idx + n - 1]) == prefix_tail:
                    blocked.add(int(generated_ids[idx + n - 1]))
            for blk_id in blocked:
                if 0 <= blk_id < vocab:
                    out[blk_id] -= 6.0
        elif n == 1 and generated_ids:
            last_id = int(generated_ids[-1])
            if 0 <= last_id < vocab:
                out[last_id] -= 4.0

        # Boost domain-relevant tokens
        for b_id in self.boost_ids:
            if 0 <= b_id < vocab and math.isfinite(out[b_id]):
                out[b_id] += self.boost_bias

        # Escalate urgency for unsatisfied required tokens as budget runs out
        if self.required_ids:
            seen = set(int(x) for x in generated_ids)
            missing = [r_id for r_id in self.required_ids if r_id not in seen and 0 <= r_id < vocab]
            if missing:
                if steps_remaining < len(missing):
                    raise ValueError("remaining budget cannot satisfy required grammar tokens")
                urgency = self.boost_bias * (1.0 + float(len(missing)) / max(1.0, float(steps_remaining)))
                if steps_remaining <= len(missing):
                    # Force next token from missing required set when budget is tight
                    for i in range(vocab):
                        if i not in missing:
                            out[i] = -math.inf
                        else:
                            out[i] += urgency
                else:
                    for r_id in missing:
                        if math.isfinite(out[r_id]):
                            out[r_id] += urgency

        # Never restore forbidden tokens when the constraints are impossible.
        if not any(math.isfinite(value) for value in out):
            raise ValueError("grammar constraints mask every token")
        if any(math.isnan(value) or value == math.inf for value in out):
            raise ValueError("grammar biases exceeded finite logit bounds")
        return out


def lookahead_jacobi_decode(
    verifier: object,
    drafts: Sequence[object] | object,
    prefix: Sequence[int],
    n: int,
    *,
    lookahead_window: int = 4,
    max_jacobi_iters: int = 3,
    logit_processor: GrammarBudgetLogitProcessor | None = None,
) -> dict[str, object]:
    """Multi-Branch Lookahead Jacobi Speculative Decoding with N-gram Trajectory Cache.

    Combines multiple draft branches with Jacobi fixed-point
    lookahead iterations and an online n-gram trajectory cache populated from
    Jacobi verification steps. Published tokens follow the verifier's greedy
    or constrained choices; speed depends on the backend and has not been
    established by this coordinator.
    """
    if type(n) is not int or not 0 <= n <= _MAX_LOOKAHEAD_TOKENS:
        raise ValueError(f"n must be an integer in [0, {_MAX_LOOKAHEAD_TOKENS}]")
    if isinstance(drafts, (list, tuple)) and len(drafts) > _MAX_DRAFT_MODELS:
        raise ValueError(f"at most {_MAX_DRAFT_MODELS} draft models are allowed")
    draft_list = [drafts] if not isinstance(drafts, (list, tuple)) else list(drafts)
    draft_list = [d for d in draft_list if d is not None]
    if not draft_list:
        draft_list = [verifier]
    vocab = getattr(verifier, "V", None)
    if type(vocab) is not int or vocab <= 0:
        raise ValueError("verifier vocabulary size must be a positive integer")
    for d in draft_list:
        if type(getattr(d, "V", None)) is not int or d.V != vocab:
            raise ValueError("all draft models must share vocabulary size V with verifier")

    if (not isinstance(prefix, Sequence) or not 1 <= len(prefix) <= _MAX_PREFIX_TOKENS
            or any(type(token) is not int or not 0 <= token < vocab for token in prefix)):
        raise ValueError("lookahead context must contain bounded in-vocabulary token IDs")
    context = list(prefix)

    if type(lookahead_window) is not int or not 1 <= lookahead_window <= 8:
        raise ValueError("lookahead_window must be an integer in [1, 8]")
    if type(max_jacobi_iters) is not int or not 1 <= max_jacobi_iters <= 6:
        raise ValueError("max_jacobi_iters must be an integer in [1, 6]")
    win, iters = lookahead_window, max_jacobi_iters
    ngram_pool: dict[tuple[int, int], list[int]] = {}
    published: list[int] = []
    total_proposed = 0
    total_accepted = 0
    jacobi_converged_steps = 0
    branch_wins: dict[int, int] = {i: 0 for i in range(-1, len(draft_list))}

    def _select_token(model: object, seq: Sequence[int], rem: int) -> int:
        ctx_len = int(getattr(model, "ctx", 6) or 6)
        w_seq = [int(x) for x in seq][-ctx_len:] or [0]
        raw_logits = list(model._logits(w_seq))
        if len(raw_logits) != vocab or any(
            not isinstance(value, (int, float)) or isinstance(value, bool)
            or math.isnan(value) or value == math.inf for value in raw_logits
        ):
            raise ValueError("model logits must match the vocabulary and contain finite values or masks")
        if logit_processor is not None:
            raw_logits = logit_processor.process(
                raw_logits,
                # seq already contains every published token and any
                # speculative branch suffix. Do not count the former twice.
                list(seq[len(prefix):]),
                steps_remaining=max(1, rem),
            )
        if len(raw_logits) != vocab or not any(math.isfinite(value) for value in raw_logits):
            raise ValueError("lookahead policy masks every token or changes the vocabulary")
        if any(math.isnan(value) or value == math.inf for value in raw_logits):
            raise ValueError("lookahead policy produced non-finite logits")
        return max(range(len(raw_logits)), key=lambda idx: (raw_logits[idx], -idx))

    while len(published) < n:
        room = min(win, n - len(published))
        candidate_branches: list[tuple[int, list[int]]] = []

        # Branch -1: N-gram lookahead trajectory cache proposal if available
        if len(context) >= 2:
            key2 = (context[-2], context[-1])
            cached_cont = ngram_pool.get(key2)
            if cached_cont:
                candidate_branches.append((-1, list(cached_cont[:room])))

        # Branches 0..K-1: Draft models with bounded Jacobi refinement
        for d_idx, d_model in enumerate(draft_list):
            cur = list(context)
            guess: list[int] = []
            for step_i in range(room):
                tok = _select_token(d_model, cur, n - len(published) - step_i)
                guess.append(tok)
                cur.append(tok)
            # Jacobi fixed-point refinement over the lookahead window
            for _ in range(iters - 1):
                refined: list[int] = []
                converged = True
                for pos in range(room):
                    prefix_slice = context + guess[:pos]
                    new_tok = _select_token(d_model, prefix_slice, n - len(published) - pos)
                    if new_tok != guess[pos]:
                        converged = False
                    refined.append(new_tok)
                # Harvest 2-gram -> continuation into lookahead pool
                full_traj = context[-2:] + guess
                for k_i in range(len(full_traj) - 2):
                    k2 = (full_traj[k_i], full_traj[k_i + 1])
                    ngram_pool[k2] = full_traj[k_i + 2:k_i + 2 + win]
                guess = refined
                if converged:
                    jacobi_converged_steps += 1
                    break
            candidate_branches.append((d_idx, guess))

        # Verify all candidate branches against the authoritative verifier and pick longest accepted prefix
        best_branch_id = 0
        best_accepted: list[int] = []

        for b_id, branch_tokens in candidate_branches:
            total_proposed += len(branch_tokens)
            acc: list[int] = []
            v_cursor = list(context)
            for step_i, b_tok in enumerate(branch_tokens):
                rem = n - len(published) - step_i
                v_tok = _select_token(verifier, v_cursor, rem)
                if len(v_cursor) >= 2:
                    ngram_pool[(v_cursor[-2], v_cursor[-1])] = [v_tok]
                if v_tok == b_tok:
                    acc.append(b_tok)
                    v_cursor.append(b_tok)
                else:
                    break
            if len(acc) > len(best_accepted):
                best_accepted = acc
                best_branch_id = b_id

        if best_accepted:
            branch_wins[best_branch_id] = branch_wins.get(best_branch_id, 0) + 1
            total_accepted += len(best_accepted)
            for tok in best_accepted:
                if len(published) < n:
                    context.append(tok)
                    published.append(tok)
        if len(best_accepted) < room and len(published) < n:
            # A different branch may have rejected earlier at a different
            # prefix. Recompute from the actual accepted context so a stale
            # fallback can never become an authoritative output token.
            fallback_tok = _select_token(verifier, context, n - len(published))
            context.append(fallback_tok)
            published.append(fallback_tok)

    itos = list(getattr(verifier, "itos", ()))
    text = " ".join(itos[t] if 0 <= t < len(itos) else "<unk>" for t in published)
    return {
        "text": text,
        "token_ids": tuple(published),
        "proposed": total_proposed,
        "accepted": total_accepted,
        "acceptance_rate": round(total_accepted / max(1, total_proposed), 4),
        "jacobi_converged_steps": jacobi_converged_steps,
        "ngram_pool_size": len(ngram_pool),
        "branch_wins": branch_wins,
    }


__all__ = [
    "GrammarBudgetLogitProcessor",
    "SpeculationResult",
    "SpeculativeDecoder",
    "cooperative_speculative",
    "greedy_speculative",
    "lookahead_jacobi_decode",
]
