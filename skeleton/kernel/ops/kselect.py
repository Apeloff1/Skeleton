"""Pick a social kernel family from profile + sequence length.

tight/mobile + long ctx → linattn or sparse
decode + long KV → flashdec + pagekv
spec draft → treeattn + specdec
embed path → ragged
"""
from __future__ import annotations

from typing import Any, Dict


def pick(*, profile: str = "mobile", seq: int = 8, spec: bool = False,
         embed: bool = False, kv: int = 0) -> Dict[str, Any]:
    p = str(profile or "mobile")
    n = max(0, int(seq))
    k = max(n, int(kv))
    if embed:
        fam = "ragged"
    elif spec:
        fam = "treeattn"
    elif p in {"tight", "mobile"} and k >= 32:
        fam = "linattn"
    elif k >= 16:
        fam = "flashdec"
    elif k >= 8:
        fam = "sparseattn"
    else:
        fam = "gqa"
    return {
        "kind": "kernel-select",
        "family": fam,
        "profile": p,
        "seq": n,
        "kv": k,
        "stored_prose": 0,
    }
