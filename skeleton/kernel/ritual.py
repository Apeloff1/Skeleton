"""One card for the whole kernel stack."""
from __future__ import annotations

from typing import Any, Dict


def card() -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, snapshot
    from skeleton.kernel.ops.catalog import Catalog
    from skeleton.kernel.profiles import card as profiles_card

    boot()
    bank = snapshot()
    blk = {}
    live_stock = {}
    try:
        from skeleton.kernel.bank import get
        b = get("block")
        if b is not None and hasattr(b, "forward"):
            blk = b.forward(["plan", "tensor"])
        s = get("stock_live")
        if s is not None and hasattr(s, "tick"):
            live_stock = s.tick("ritual")
    except Exception:
        pass
    return {
        "kind": "kernel-ritual",
        "profile": bank.get("profile"),
        "n": bank.get("n"),
        "names": bank.get("names") or list((bank.get("kernels") or {}).keys()),
        "catalog": Catalog().card(),
        "block": blk,
        "stock_live": live_stock,
        "profiles": profiles_card(),
        "stored_prose": 0,
    }
