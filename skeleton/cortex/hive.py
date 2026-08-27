"""Hive merkle-sync — two cortices share the MODELS, not the tape.

`merkle_card` is the small identity of an organism (MoE fingerprint,
transformer steps, own size, callosum fires). `bundle` is the guts
(experts + callosum + bpe + heads via moe snapshot). `pull` replaces
dst experts iff the merkle differs — that is acquire-at-hive-scale.
Identical merkle is a no-op (skip_search for nets). Pure Python.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def merkle_card(neo) -> Dict[str, Any]:
    moe = getattr(neo, "moe", None)
    xf = getattr(neo, "transformer", None)
    cc = getattr(neo, "callosum", None)
    bpe = getattr(neo, "bpe", None)
    return {
        "moe_fp": moe.fingerprint() if moe is not None else "",
        "own": int(getattr(getattr(neo, "own", None), "size", 0) or 0),
        "acquired": dict(getattr(neo, "acquired", {}) or {}),
        "transformer_steps": int(getattr(xf, "steps", 0) or 0),
        "transformer_fitted": int(getattr(xf, "fitted", 0) or 0),
        "callosum_fires": int(getattr(cc, "fires", 0) or 0),
        "callosum_hebbs": int(getattr(cc, "hebbs", 0) or 0),
        "bpe_merges": int(len(getattr(bpe, "merges", ()) or ())),
        "rl_steps": int(getattr(getattr(neo, "rl", None), "steps", 0) or 0),
        "seq_fires": int(getattr(cc, "seq_fires", 0) or 0),
        "n_layers": int(getattr(xf, "n_layers", 0) or 0),
        "n_heads": int(getattr(xf, "n_heads", 0) or 0),
        "device": str(getattr(xf, "device", "cpu") or "cpu"),
        "resident": bool(getattr(xf, "resident", False)),
        "devil": bool(getattr(neo, "_surpass", None)),
    }


def bundle(neo) -> Dict[str, Any]:
    """Guts a hive peer can pull. Merkle first, then the nets."""
    card = merkle_card(neo)
    moe = getattr(neo, "moe", None)
    cc = getattr(neo, "callosum", None)
    bpe = getattr(neo, "bpe", None)
    xf = getattr(neo, "transformer", None)
    return {
        **card,
        "moe": moe.snapshot() if moe is not None else None,
        "callosum": cc.snapshot() if cc is not None else None,
        "bpe": bpe.snapshot() if bpe is not None and hasattr(bpe, "snapshot") else None,
        "transformer": xf.snapshot() if xf is not None and hasattr(xf, "snapshot") else None,
    }


def pull(dst, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace dst experts iff merkle differs. Returns whether pulled."""
    payload = payload or {}
    src_fp = str(payload.get("moe_fp") or "")
    dst_fp = dst.moe.fingerprint() if getattr(dst, "moe", None) is not None else ""
    if not src_fp or src_fp == dst_fp or not payload.get("moe"):
        return {
            "pulled": 0,
            "reason": "same" if src_fp == dst_fp else "empty",
            "moe_fp": dst_fp,
            "src_fp": src_fp,
        }
    from skeleton.cortex.moe import ExpertBank
    dst.moe = ExpertBank.from_snapshot(payload["moe"])
    if payload.get("callosum") is not None:
        from skeleton.cortex.callosum import CorpusCallosum
        dst.callosum = CorpusCallosum.from_snapshot(payload["callosum"])
    if payload.get("bpe") is not None:
        from skeleton.cortex.bpe import BytePairEncoder
        dst.bpe = BytePairEncoder.from_snapshot(payload["bpe"])
    pulled_xf = 0
    if payload.get("transformer") is not None and hasattr(dst, "transformer"):
        try:
            from skeleton.cortex.transformer import TinyTransformer
            dst.transformer = TinyTransformer.from_snapshot(payload["transformer"])
            pulled_xf = 1
        except Exception:
            pulled_xf = 0
    return {
        "pulled": 1,
        "reason": "merkle-diff",
        "moe_fp": dst.moe.fingerprint(),
        "src_fp": src_fp,
        "transformer": pulled_xf,
        "card": merkle_card(dst),
    }
