"""One card for the whole kernel stack."""
from __future__ import annotations

from typing import Any, Dict


def card(*, live: bool = False) -> Dict[str, Any]:
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
    out = {
        "kind": "kernel-ritual",
        "profile": bank.get("profile"),
        "n": bank.get("n"),
        "names": bank.get("names") or list((bank.get("kernels") or {}).keys()),
        "catalog": Catalog().card(),
        "block": blk,
        "stock_live": live_stock,
        "profiles": profiles_card(),
        "scoreboard": __import__("skeleton.kernel.scoreboard", fromlist=["card"]).card(),
        "coverage": __import__("skeleton.kernel.coverage", fromlist=["card"]).card(),
        "runtime": __import__("skeleton.organism.runtime", fromlist=["last"]).last(),
        "conductor": {},
        "observe": __import__("skeleton.organism.observe", fromlist=["card"]).card(),
        "live": int(live),
        "stored_prose": 0,
    }
    try:
        from skeleton.organism.conductor import decide
        d = decide()
        out["conductor"] = {"code": d.get("code"), "why": d.get("why"), "horizon": d.get("horizon")}
    except Exception:
        pass
    if live:
        try:
            from skeleton.kernel.bank import get
            from skeleton.kernel.orchestrator import Orchestrator
            orch = get("orch") or Orchestrator()
            walked = orch.dispatch("plan tensor ttk")
            out["orch"] = {"n": walked.get("n"), "runs": walked.get("runs")}
        except Exception:
            out["orch"] = {}
        try:
            from skeleton.organism.runtime import dispatch as live_dispatch
            rt = live_dispatch(stimulus="plan tensor ttk")
            out["runtime"] = {"n": rt.get("n"), "ctx_n": rt.get("ctx_n"), "profile": rt.get("profile")}
        except Exception:
            pass
    return out
