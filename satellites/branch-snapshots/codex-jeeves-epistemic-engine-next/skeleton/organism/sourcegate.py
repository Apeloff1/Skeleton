"""Kernel may land only if a SOTA pointer names it."""
from __future__ import annotations

from typing import Any, Dict


def allowed(name: str) -> bool:
    from skeleton.social.sources import SOTA_POINTERS
    n = str(name or "").lower().replace("_", "-")
    if not n:
        return False
    for row in SOTA_POINTERS:
        blob = " ".join(str(row.get(k) or "") for k in ("topic", "url")).lower()
        if n in blob or n.replace("-", "") in blob.replace("-", ""):
            return True
    return False


def card(name: str) -> Dict[str, Any]:
    ok = allowed(name)
    return {"kind": "source-gate", "name": name, "ok": int(ok), "stored_prose": 0}
