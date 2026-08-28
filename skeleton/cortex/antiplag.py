"""Near-duplicate guard — Broder w-shingling + token Jaccard.

Industry default for "is this a copy" without storing the source:
4-word shingles, Jaccard on the shingle sets.
"""
from __future__ import annotations

import re
from typing import Tuple

from skeleton.cortex.laws import LawError

_TOKEN = re.compile(r"[a-z0-9]+")
MAX_JACCARD = 0.28
MAX_SHINGLE = 0.12
W = 4


def tokens(text: str) -> Tuple[str, ...]:
    return tuple(_TOKEN.findall((text or "").lower()))


def shingles(text: str, w: int = W) -> set:
    seq = tokens(text)
    if len(seq) < w:
        return set()
    return {seq[i:i + w] for i in range(0, len(seq) - w + 1)}


def score(house: str, source: str) -> dict:
    a, b = tokens(house), tokens(source)
    if not a or not b:
        return {"jaccard": 0.0, "shingle": 0.0, "copy": False, "method": "broder-w4"}
    ja, jb = set(a), set(b)
    jacc = len(ja & jb) / max(1, len(ja | jb))
    sa, sb = shingles(house), shingles(source)
    sh = (len(sa & sb) / max(1, len(sa | sb))) if sa and sb else 0.0
    return {
        "jaccard": round(jacc, 4),
        "shingle": round(sh, 4),
        "copy": jacc >= MAX_JACCARD or sh >= MAX_SHINGLE,
        "method": "broder-w4",
    }


def guard(house: str, source: str) -> str:
    s = score(house or "", source or "")
    if s["copy"]:
        raise LawError("cite-do-not-copy", f"jaccard={s['jaccard']} shingle={s['shingle']}")
    return house or ""


def distill_dialect(title: str, era: str = "", genres=None) -> str:
    bits = [str(title or "game").lower()]
    if era:
        bits.append(str(era))
    for g in genres or ():
        bits.append(str(g).lower())
    bits.append("plan tensor ttk hp dps")
    return " ".join(bits)
