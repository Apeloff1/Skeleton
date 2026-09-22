"""Hot kernels — stages that actually ran on the last walk."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from skeleton.kernel.persist import load


def rank(*, root=None) -> Dict[str, Any]:
    last = load(root=root)
    counts: Counter[str] = Counter()
    for row in last.get("trace") or []:
        counts[str(row.get("stage") or "")] += 1
    hot: List[str] = [k for k, _ in counts.most_common() if k]
    return {
        "kind": "kernel-hot",
        "hot": hot,
        "n": len(hot),
        "runs": last.get("runs") or 0,
        "mix": __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card(),
        "stored_prose": 0,
    }
