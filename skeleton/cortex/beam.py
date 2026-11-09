"""Beam search. Width 1 is greedy. Token ids are the currency."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from skeleton.cortex.attn import softmax
from skeleton.cortex.port import tokens


def _encode(lm, prefix: str | Sequence[str]) -> List[int]:
    if isinstance(prefix, str):
        body = list(tokens(prefix))
    else:
        body = [str(t) for t in prefix]
    ids = [lm._id(t) for t in body] if hasattr(lm, "_id") else []
    return ids or [int(getattr(lm, "unk", 0) or 0)]


def _logits(lm, ids: Sequence[int]) -> List[float]:
    window = list(ids[-int(getattr(lm, "ctx", len(ids) or 1) or 1):] or ids)
    if hasattr(lm, "_logits_window"):
        return list(lm._logits_window(window, None))
    return list(lm._logits(window))


def _tok(lm, idx: int) -> str:
    itos = getattr(lm, "itos", None) or []
    return str(itos[idx]) if 0 <= idx < len(itos) else "__unk__"


def beam_search(lm, prefix: str | Sequence[str], *, n: int = 8, width: int = 4, length_penalty: float = 0.6) -> Dict[str, Any]:
    w, steps = max(1, int(width)), max(1, int(n))
    lp = max(0.0, float(length_penalty))
    start = _encode(lm, prefix)
    beam: List[Tuple[float, List[int]]] = [(0.0, list(start))]
    for _ in range(steps):
        cand: List[Tuple[float, List[int]]] = []
        for score, ids in beam:
            logp = [math.log(max(p, 1e-12)) for p in softmax(_logits(lm, ids))]
            for idx in sorted(range(len(logp)), key=lambda i: -logp[i])[:w]:
                cand.append((score + logp[idx], ids + [idx]))
        cand.sort(key=lambda kv: -kv[0])
        beam = cand[:w]
    finished = []
    for score, ids in beam:
        gen = ids[len(start):]
        norm = score / (max(1, len(gen)) ** lp) if lp else score
        finished.append((norm, ids))
    finished.sort(key=lambda kv: -kv[0])
    ranked = []
    for score, ids in finished:
        gen = ids[len(start):]
        ranked.append({"text": " ".join(_tok(lm, i) for i in gen), "tokens": [_tok(lm, i) for i in gen],
                       "score": round(float(score), 6), "ids": list(gen)})
    winner = ranked[0] if ranked else {"text": "", "tokens": [], "score": 0.0, "ids": []}
    return {"width": w, "n": steps, "length_penalty": lp, "winner": winner["text"], "score": winner["score"], "beams": ranked}


def greedy_beam(lm, prefix: str, *, n: int = 8) -> Tuple[str, ...]:
    out = beam_search(lm, prefix, n=n, width=1, length_penalty=0.0)
    return tuple((out.get("beams") or [{}])[0].get("tokens") or [])
