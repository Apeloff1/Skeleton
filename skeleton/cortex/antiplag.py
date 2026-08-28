"""Anti-plagiarism — house text must not be a copy of a source page.

Parse-on-demand may *read* a source. It may not emit or persist a
near-copy. Similarity is token Jaccard + 8-gram overlap. Thresholds
are tight on purpose.
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

from skeleton.cortex.laws import LawError

_TOKEN = re.compile(r"[a-z0-9]+")
MAX_JACCARD = 0.28
MAX_NGRAM = 0.18
N = 8


def tokens(text: str) -> Tuple[str, ...]:
    return tuple(_TOKEN.findall((text or "").lower()))


def _ngrams(toks: Iterable[str], n: int = N) -> set:
    seq = tuple(toks)
    if len(seq) < n:
        return set()
    return {seq[i:i + n] for i in range(0, len(seq) - n + 1)}


def score(house: str, source: str) -> dict:
    a, b = tokens(house), tokens(source)
    if not a or not b:
        return {"jaccard": 0.0, "ngram": 0.0, "copy": False}
    ja = set(a)
    jb = set(b)
    jacc = len(ja & jb) / max(1, len(ja | jb))
    na, nb = _ngrams(a), _ngrams(b)
    ng = (len(na & nb) / max(1, len(na | nb))) if na and nb else 0.0
    return {"jaccard": round(jacc, 4), "ngram": round(ng, 4), "copy": jacc >= MAX_JACCARD or ng >= MAX_NGRAM}


def guard(house: str, source: str) -> str:
    """Return house text if it is not a copy. Raise LawError if it is."""
    s = score(house or "", source or "")
    if s["copy"]:
        raise LawError("cite-do-not-copy", f"jaccard={s['jaccard']} ngram={s['ngram']}")
    return house or ""


def distill_dialect(title: str, era: str = "", genres=None) -> str:
    """House-authored pointer language. Never a paraphrase of a blurb."""
    bits = [str(title or "game").lower()]
    if era:
        bits.append(str(era))
    for g in genres or ():
        bits.append(str(g).lower())
    bits.append("plan tensor ttk hp dps")
    return " ".join(bits)
