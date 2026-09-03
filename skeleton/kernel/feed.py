"""Feed — follow-bag tokens into the orchestrator."""
from __future__ import annotations

from typing import List


def tokens(text: str = "", *, n: int = 4) -> List[str]:
    base = [t for t in (text or "").split() if len(t) >= 3][:n]
    try:
        from skeleton.organism.follow import load
        bag = load().get("bag") or {}
        extra = [k for k, _ in sorted(bag.items(), key=lambda kv: -int(kv[1])) if len(k) >= 3]
        for t in extra:
            if t not in base:
                base.append(t)
            if len(base) >= n:
                break
    except Exception:
        pass
    return base or ["plan", "tensor"]
