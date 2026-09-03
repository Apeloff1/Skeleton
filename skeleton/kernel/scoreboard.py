"""Scoreboard — one card per live kernel."""
from __future__ import annotations

from typing import Any, Dict


def card() -> Dict[str, Any]:
    from skeleton.kernel.bank import boot, live, snapshot

    boot()
    snap = snapshot()
    rows: Dict[str, Any] = {}
    for name, inst in live().items():
        if hasattr(inst, "card"):
            try:
                rows[name] = inst.card()
            except Exception as exc:
                rows[name] = {"kind": "err", "err": type(exc).__name__, "stored_prose": 0}
        else:
            rows[name] = {"kind": type(inst).__name__, "stored_prose": 0}
    out = {
        "kind": "kernel-scoreboard",
        "profile": snap.get("profile"),
        "n": len(rows),
        "rows": rows,
        "stored_prose": 0,
    }
    try:
        from skeleton.kernel.persist import save_board
        save_board(out)
    except Exception:
        pass
    try:
        out["mix"] = __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card()
    except Exception:
        pass
    return out
