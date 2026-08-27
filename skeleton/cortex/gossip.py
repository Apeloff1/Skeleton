"""Weight gossip. α-mix two same-shape transformers. α=0 is a no-op."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from skeleton.cortex.hive import merkle_card


def _mix_vec(a: Sequence[float], b: Sequence[float], alpha: float) -> List[float]:
    if len(a) != len(b):
        return list(a)
    ia = 1.0 - alpha
    return [ia * x + alpha * y for x, y in zip(a, b)]


def _mix_mat(A: List[List[float]], B: List[List[float]], alpha: float) -> List[List[float]]:
    if not A or not B or len(A) != len(B) or len(A[0]) != len(B[0]):
        return [list(row) for row in A]
    return [_mix_vec(ra, rb, alpha) for ra, rb in zip(A, B)]


def mix_blocks(dst_blk: Dict[str, Any], src_blk: Dict[str, Any], alpha: float) -> Dict[str, Any]:
    out = dict(dst_blk)
    for key in ("Wq", "Wk", "Wv", "Wo", "W1", "W2", "b1", "b2", "ln1_g", "ln1_b", "ln2_g", "ln2_b"):
        dv, sv = dst_blk.get(key), src_blk.get(key)
        if isinstance(dv, list) and dv and isinstance(dv[0], list):
            out[key] = _mix_mat(dv, sv or dv, alpha)
        elif isinstance(dv, list):
            out[key] = _mix_vec(dv, sv or dv, alpha)
    return out


def mix_snapshots(dst: Dict[str, Any], src: Dict[str, Any], alpha: float) -> Dict[str, Any]:
    a = max(0.0, min(1.0, float(alpha)))
    out = dict(dst)
    for key in ("E", "P", "Wout"):
        if isinstance(dst.get(key), list) and isinstance(src.get(key), list):
            out[key] = _mix_mat(dst[key], src[key], a)
    if isinstance(dst.get("bout"), list) and isinstance(src.get("bout"), list):
        out["bout"] = _mix_vec(dst["bout"], src["bout"], a)
    d_layers, s_layers = list(dst.get("layers") or []), list(src.get("layers") or [])
    if d_layers and s_layers and len(d_layers) == len(s_layers):
        out["layers"] = [mix_blocks(d, s, a) for d, s in zip(d_layers, s_layers)]
    return out


def gossip(dst_lm, src_lm, *, alpha: float = 0.5, keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    if dst_lm is None or src_lm is None:
        return {"gossiped": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"gossiped": 0, "reason": "dim-mismatch"}
    if int(getattr(dst_lm, "n_layers", 0) or 0) != int(getattr(src_lm, "n_layers", 0) or 0):
        return {"gossiped": 0, "reason": "depth-mismatch"}
    a = max(0.0, min(1.0, float(alpha)))
    restored = type(dst_lm).from_snapshot(mix_snapshots(dst_lm.snapshot(), src_lm.snapshot(), a))
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    return {"gossiped": 1, "alpha": a, "n_layers": int(dst_lm.n_layers), "dim": int(dst_lm.dim),
            "keys": list(keys or ("E", "P", "Wout", "layers"))}


def gossip_cortices(dst, src, *, alpha: float = 0.5) -> Dict[str, Any]:
    before = merkle_card(dst)
    info = gossip(getattr(dst, "transformer", None), getattr(src, "transformer", None), alpha=alpha)
    after = merkle_card(dst)
    info["before_steps"] = before.get("transformer_steps")
    info["after_steps"] = after.get("transformer_steps")
    info["card"] = after
    return info
