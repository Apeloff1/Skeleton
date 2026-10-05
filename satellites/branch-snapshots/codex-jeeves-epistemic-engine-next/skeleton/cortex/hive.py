"""Hive merkle-sync — two cortices share the MODELS, not the tape.

`merkle_card` is the small identity of an organism (MoE fingerprint,
transformer steps, own size, callosum fires). `bundle` is the guts
(experts + callosum + bpe + heads via moe snapshot). `pull` replaces
dst experts iff the merkle differs — that is acquire-at-hive-scale.
Identical merkle is a no-op (skip_search for nets). Pure Python.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _e_fp(xf) -> str:
    if xf is None:
        return ""
    row = (getattr(xf, "E", None) or [[0.0]])[0][:4]
    return ",".join(f"{float(x):.5f}" for x in row)


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
        "tied": bool(getattr(xf, "tied", False)),
        "norm": str(getattr(xf, "norm", "ln") or "ln"),
        "ffn_kind": str(getattr(xf, "ffn_kind", "gelu") or "gelu"),
        "neo_rms": {
            "norm": str(getattr(getattr(neo, "neo_rms", None), "norm", "") or ""),
            "ffn_kind": str(getattr(getattr(neo, "neo_rms", None), "ffn_kind", "") or ""),
            "steps": int(getattr(getattr(neo, "neo_rms", None), "steps", 0) or 0),
            "e_fp": _e_fp(getattr(neo, "neo_rms", None)),
            "lora": bool(getattr(getattr(neo, "neo_rms", None), "lora", None) is not None),
        },
        "lora": (xf.lora.to_dict() if xf is not None and getattr(xf, "lora", None) is not None else None),
        "models": sorted(getattr(getattr(neo, "own", None), "models", {}) or {}),
        "e_fp": _e_fp(xf),
    }


def consensus(a, b, *, texts=None) -> Dict[str, Any]:
    """Lower finite ppl inherits the house. Loser pulls the winner bundle."""
    from skeleton.cortex.curriculum import CORE_PAIRS
    corpus = list(texts or [s for s, _ in list(CORE_PAIRS)[:6]])

    def _p(neo) -> float:
        xf = getattr(neo, "transformer", None)
        if xf is None or not hasattr(xf, "perplexity"):
            return float("inf")
        try:
            return float(xf.perplexity(corpus))
        except Exception:
            return float("inf")

    pa, pb = _p(a), _p(b)
    if pa <= pb:
        winner, loser, wp = a, b, pa
    else:
        winner, loser, wp = b, a, pb
    info = pull(loser, bundle(winner))
    info["winner_ppl"] = wp
    info["ppl"] = {"a": pa, "b": pb}
    info["consensus"] = 1
    return info


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
        "lora": (xf.lora.snapshot() if xf is not None and getattr(xf, "lora", None) is not None else None),
        "neo_rms_weights": (getattr(neo, "neo_rms", None).snapshot()
                           if getattr(neo, "neo_rms", None) is not None else None),
        "lora_rms": (getattr(getattr(neo, "neo_rms", None), "lora", None).snapshot()
                     if getattr(getattr(neo, "neo_rms", None), "lora", None) is not None else None),
    }


def pull(dst, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace dst experts iff merkle differs. Returns whether pulled."""
    payload = payload or {}
    src_fp = str(payload.get("moe_fp") or "")
    dst_card = merkle_card(dst)
    dst_fp = dst_card.get("moe_fp") or ""
    same_moe = bool(src_fp) and src_fp == dst_fp
    same_e = str(payload.get("e_fp") or "") == str(dst_card.get("e_fp") or "")
    same_rms = str((payload.get("neo_rms") or {}).get("e_fp") or "") == str((dst_card.get("neo_rms") or {}).get("e_fp") or "")
    if same_moe and same_e and same_rms:
        return {
            "pulled": 0,
            "reason": "same" if src_fp == dst_fp else "empty",
            "moe_fp": dst_fp,
            "src_fp": src_fp,
        }
    if not payload.get("moe") and not payload.get("transformer") and not payload.get("neo_rms_weights"):
        return {"pulled": 0, "reason": "empty", "moe_fp": dst_fp, "src_fp": src_fp}
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
            if payload.get("lora") is not None:
                from skeleton.cortex.lora import LoRABank
                dst.transformer.lora = LoRABank.from_snapshot(payload["lora"])
        except Exception:
            pulled_xf = 0
    pulled_rms = 0
    if payload.get("neo_rms_weights") is not None:
        try:
            from skeleton.cortex.transformer import TinyTransformer
            dst.neo_rms = TinyTransformer.from_snapshot(payload["neo_rms_weights"])
            pulled_rms = 1
            if payload.get("lora_rms") is not None:
                from skeleton.cortex.lora import LoRABank
                dst.neo_rms.lora = LoRABank.from_snapshot(payload["lora_rms"])
        except Exception:
            pulled_rms = 0
    return {
        "pulled": 1,
        "reason": "merkle-diff",
        "moe_fp": dst.moe.fingerprint(),
        "src_fp": src_fp,
        "transformer": pulled_xf,
        "neo_rms": pulled_rms,
        "card": merkle_card(dst),
    }
