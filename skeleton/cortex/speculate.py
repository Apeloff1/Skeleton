"""Speculative decode — PFC drafts, neo verifies. Succession, not hope.

The small mouth (PFC n-gram / skip-gram) proposes a continuation.
The neo transformer scores each drafted token. A draft token is
accepted iff it sits in the neo's top-k. Rejection stops the run and
the neo samples the remainder itself. Accepted length is the proof
the small model is a draft of the large one, not a peer.

Devil gene: when own-lm is armed, speculate prefers neo's own decode
as the verifier even if a bound PFC backend changed. Veto still wins
elsewhere; this file never speaks to the operator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from skeleton.cortex.attn import sample_logits, softmax
from skeleton.cortex.port import tokens


def _pfc_draft(neo, prefix: str, n: int, seed: int) -> List[str]:
    pfc = (getattr(neo, "slots", {}) or {}).get("pfc")
    lm = getattr(pfc, "lm", None) if pfc is not None else None
    if lm is None or not hasattr(lm, "generate"):
        return []
    raw = lm.generate(prefix, n=n, seed=seed)
    return [str(t) for t in raw]


def _neo_topk(xf, running: Sequence[str], k: int) -> List[int]:
    ids = [xf._id(t) for t in running] or [xf.unk]
    window = ids[-xf.ctx:]
    logits = xf._logits(window)
    p = softmax(logits)
    order = sorted(range(len(p)), key=lambda i: -p[i])
    return order[: max(1, int(k))]


def speculate(
    neo,
    prefix: str,
    *,
    n: int = 8,
    seed: int = 0,
    k: int = 4,
) -> Dict[str, Any]:
    """Draft from PFC, verify on neo. Returns accepted / drafted / rest."""
    xf = getattr(neo, "transformer", None)
    if xf is None:
        return {"accepted": 0, "drafted": 0, "ratio": 0.0, "rest": [], "draft": []}
    draft_all = _pfc_draft(neo, prefix, n, seed)
    body = list(tokens(prefix))
    if draft_all[:len(body)] == body:
        draft = draft_all[len(body):]
    else:
        draft = list(draft_all)
    running = list(body)
    accepted: List[str] = []
    rejected: Optional[str] = None
    for tok in draft:
        top = _neo_topk(xf, running, k)
        if xf._id(tok) in top:
            accepted.append(tok)
            running.append(tok)
        else:
            rejected = tok
            break
    rest: List[str] = []
    remain = max(0, int(n) - len(accepted))
    if remain and rejected is not None:
        # neo samples the remainder from its own mouth
        cont = xf.generate(" ".join(running) if running else prefix, n=remain, seed=seed + 1)
        rest = [str(t) for t in cont]
    drafted_n = len(draft)
    return {
        "accepted": len(accepted),
        "drafted": drafted_n,
        "rejected": rejected,
        "ratio": (len(accepted) / drafted_n) if drafted_n else 0.0,
        "k": int(k),
        "draft": draft,
        "accepted_tokens": accepted,
        "rest": rest,
        "verifier": "neo-transformer",
        "drafter": "pfc",
    }


def greedy_decode(xf, prefix: str, n: int = 8) -> List[str]:
    """temperature=0 path. Identity: sample_logits(t→0) == argmax."""
    body = list(tokens(prefix))
    ids = [xf._id(t) for t in body] or [xf.unk]
    out = list(ids)
    for _ in range(max(1, int(n))):
        window = out[-xf.ctx:]
        nxt = sample_logits(xf._logits(window), None, temperature=0.0)
        out.append(int(nxt))
    return [xf.itos[i] if 0 <= i < len(xf.itos) else "__unk__" for i in out[:n]]
