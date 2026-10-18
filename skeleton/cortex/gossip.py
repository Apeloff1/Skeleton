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
    for key in ("Wq", "Wk", "Wv", "Wo", "W1", "Wu", "W2", "b1", "bu", "b2", "ln1_g", "ln1_b", "ln2_g", "ln2_b"):
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
    if a == 0.0:
        return {"gossiped": 1, "alpha": 0.0, "n_layers": int(dst_lm.n_layers), "dim": int(dst_lm.dim),
                "keys": list(keys or ("E", "P", "Wout", "layers")), "reason": "alpha0"}
    restored = type(dst_lm).from_snapshot(mix_snapshots(dst_lm.snapshot(), src_lm.snapshot(), a))
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    return {"gossiped": 1, "alpha": a, "n_layers": int(dst_lm.n_layers), "dim": int(dst_lm.dim),
            "keys": list(keys or ("E", "P", "Wout", "layers"))}


def gossip_cortices(dst, src, *, alpha: float = 0.5) -> Dict[str, Any]:
    before = merkle_card(dst)
    info = gossip(getattr(dst, "transformer", None), getattr(src, "transformer", None), alpha=alpha)
    rms = gossip(getattr(dst, "neo_rms", None), getattr(src, "neo_rms", None), alpha=alpha)
    after = merkle_card(dst)
    info["before_steps"] = before.get("transformer_steps")
    info["after_steps"] = after.get("transformer_steps")
    info["neo_rms"] = rms
    info["card"] = after
    return info


def absorb_mouth(dst_lm, src_lm, *, alpha: float = 0.2) -> Dict[str, Any]:
    """Copy a trained (possibly shallower) mouth into dst."""
    if dst_lm is None or src_lm is None:
        return {"absorbed": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"absorbed": 0, "reason": "dim-mismatch"}
    source_training = max(
        int(getattr(src_lm, "fitted", 0) or 0),
        int(getattr(src_lm, "steps", 0) or 0),
    )
    if source_training <= 0:
        return {"absorbed": 0, "reason": "source-unfitted"}
    a = max(0.0, min(1.0, float(alpha)))
    if a == 0.0:
        return {"absorbed": 1, "alpha": 0.0, "reason": "alpha0", "layers": 0}
    ds = dst_lm.snapshot()
    ss = src_lm.snapshot()
    mixed = mix_snapshots(ds, ss, a)
    d_layers, s_layers = list(ds.get("layers") or []), list(ss.get("layers") or [])
    n = min(len(d_layers), len(s_layers))
    if n and len(d_layers) != len(s_layers):
        layers = [mix_blocks(d_layers[i], s_layers[i], a) for i in range(n)] + d_layers[n:]
        mixed["layers"] = layers
    restored = type(dst_lm).from_snapshot(mixed)
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    return {"absorbed": 1, "alpha": a, "layers": n,
            "dst_layers": int(dst_lm.n_layers), "src_layers": int(getattr(src_lm, "n_layers", 0) or 0)}


def gossip_mouths(neo, *, alpha: float = 0.25, direction: str = "rms-into-gelu") -> Dict[str, Any]:
    """Mix the two local mouths. Default: RMS/SwiGLU bleeds into the GELU primary."""
    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    if direction == "gelu-into-rms":
        info = gossip(rms, xf, alpha=alpha)
        info["direction"] = direction
        return info
    info = gossip(xf, rms, alpha=alpha)
    info["direction"] = "rms-into-gelu"
    return info


def adaptive_gossip(
    dst_lm,
    src_lm,
    corpus: Iterable[str],
    *,
    max_alpha: float = 0.5,
) -> Dict[str, Any]:
    """Perplexity-calibrated, coherence-gated weight gossip with automatic rollback."""
    import math

    if dst_lm is None or src_lm is None:
        return {"gossiped": 0, "reason": "missing"}
    if int(getattr(dst_lm, "dim", 0) or 0) != int(getattr(src_lm, "dim", 0) or 0):
        return {"gossiped": 0, "reason": "dim-mismatch"}
    if int(getattr(dst_lm, "n_layers", 0) or 0) != int(getattr(src_lm, "n_layers", 0) or 0):
        return {"gossiped": 0, "reason": "depth-mismatch"}
    texts = [t for t in corpus if isinstance(t, str) and t.strip()]
    if not texts:
        return {"gossiped": 0, "reason": "empty-corpus"}
    cap = max(0.0, min(1.0, float(max_alpha)))
    dst_before = float(dst_lm.perplexity(texts))
    src_ppl = float(src_lm.perplexity(texts))
    if not math.isfinite(dst_before) or not math.isfinite(src_ppl):
        return {"gossiped": 0, "reason": "nonfinite-ppl"}
    # Weight alpha proportional to src_lm's inverse-perplexity share.
    inv_dst = 1.0 / max(dst_before, 1e-9)
    inv_src = 1.0 / max(src_ppl, 1e-9)
    raw_share = inv_src / (inv_dst + inv_src)
    alpha = round(min(cap, max(0.05, raw_share * cap * 2.0)), 6) if cap > 0.0 else 0.0
    if alpha == 0.0:
        return {
            "gossiped": 0,
            "alpha": 0.0,
            "dst_ppl_before": round(dst_before, 6),
            "dst_ppl_after": round(dst_before, 6),
            "src_ppl": round(src_ppl, 6),
            "reason": "alpha0",
        }
    saved = dst_lm.snapshot()
    mixed = mix_snapshots(saved, src_lm.snapshot(), alpha)
    restored = type(dst_lm).from_snapshot(mixed)
    dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = restored.E, restored.P, restored.Wout, restored.bout
    dst_lm.layers, dst_lm.n_layers = restored.layers, restored.n_layers
    if getattr(dst_lm, "tied", False) and hasattr(dst_lm, "tie"):
        dst_lm.tie()
    dst_after = float(dst_lm.perplexity(texts))
    if not math.isfinite(dst_after) or dst_after > dst_before:
        rollback = type(dst_lm).from_snapshot(saved)
        dst_lm.E, dst_lm.P, dst_lm.Wout, dst_lm.bout = rollback.E, rollback.P, rollback.Wout, rollback.bout
        dst_lm.layers, dst_lm.n_layers = rollback.layers, rollback.n_layers
        if getattr(dst_lm, "tied", False) and hasattr(dst_lm, "tie"):
            dst_lm.tie()
        return {
            "gossiped": 0,
            "alpha": alpha,
            "dst_ppl_before": round(dst_before, 6),
            "dst_ppl_after": round(dst_before, 6),
            "candidate_ppl": round(dst_after, 6) if math.isfinite(dst_after) else None,
            "src_ppl": round(src_ppl, 6),
            "reason": "coherence-gate-rollback",
        }
    return {
        "gossiped": 1,
        "alpha": alpha,
        "dst_ppl_before": round(dst_before, 6),
        "dst_ppl_after": round(dst_after, 6),
        "src_ppl": round(src_ppl, 6),
        "reason": "improved",
    }


def cooperative_logits(
    models: Sequence[Any],
    ids: Sequence[int],
    *,
    weights: Optional[Sequence[float]] = None,
    caches: Optional[Sequence[Any]] = None,
) -> List[float]:
    """Fuse next-token distributions from multiple compatible models in log-prob space."""
    import math
    from skeleton.cortex.attn import softmax

    valid = [m for m in models if m is not None]
    if not valid:
        raise ValueError("cooperative_logits requires at least one model")
    vocab = int(getattr(valid[0], "V", 0) or 0)
    if vocab <= 0:
        raise ValueError("cooperative model must expose positive vocabulary size V")
    for m in valid[1:]:
        if int(getattr(m, "V", 0) or 0) != vocab:
            raise ValueError("all cooperative models must share vocabulary size V")
    if weights is None:
        w_norm = [1.0 / len(valid)] * len(valid)
    else:
        if len(weights) != len(valid):
            raise ValueError("weights length must match models length")
        raw_w = [max(0.0, float(w)) for w in weights]
        total_w = sum(raw_w)
        if total_w <= 0.0 or not math.isfinite(total_w):
            raise ValueError("weights must have a positive finite sum")
        w_norm = [w / total_w for w in raw_w]

    fused_probs = [0.0] * vocab
    for idx, model in enumerate(valid):
        ctx = int(getattr(model, "ctx", 6) or 6)
        window = [int(t) for t in ids][-ctx:] or [0]
        cache = caches[idx] if (caches is not None and idx < len(caches)) else None
        if cache is not None and hasattr(model, "_logits_window"):
            logits = list(model._logits_window(window, cache))
        else:
            logits = list(model._logits(window))
        probs = softmax(logits)
        weight = w_norm[idx]
        for v in range(vocab):
            fused_probs[v] += weight * probs[v]
    return [math.log(max(p, 1e-12)) for p in fused_probs]


def cooperative_decode(
    models: Sequence[Any],
    prefix: str,
    *,
    n: int = 12,
    seed: int = 0,
    weights: Optional[Sequence[float]] = None,
    temperature: float = 1.0,
    top_k: int = 0,
    top_p: float = 1.0,
    min_p: float = 0.0,
    use_cache: bool = True,
) -> str:
    """Cooperatively decode n tokens from a weighted ensemble of compatible models."""
    import random
    from skeleton.cortex.attn import sample_logits
    from skeleton.cortex.transformer import UNK, KVCache

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    valid = [m for m in models if m is not None]
    if not valid:
        return ""
    primary = valid[0]
    for m in valid[1:]:
        if list(getattr(m, "itos", ())) != list(getattr(primary, "itos", ())):
            raise ValueError("cooperative models must share identical token vocabularies")
    ids = list(primary._ids(prefix or "")) or [int(getattr(primary, "unk", 0))]
    caches = [
        KVCache(int(m.n_layers), int(m.ctx))
        if (use_cache and hasattr(m, "_logits_window") and not getattr(m, "use_mod", False))
        else None
        for m in valid
    ]
    rng = random.Random(int(seed) & 0xFFFFFFFF)
    generated: List[int] = []
    for _ in range(n):
        logits = cooperative_logits(valid, ids, weights=weights, caches=caches)
        nxt = int(
            sample_logits(
                logits,
                rng,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                min_p=min_p,
            )
        )
        ids.append(nxt)
        generated.append(nxt)
    itos = list(getattr(primary, "itos", ()))
    return " ".join(itos[i] if 0 <= i < len(itos) else UNK for i in generated)


def redundant_consensus_decode(
    models: Sequence[Any],
    prefix: str,
    *,
    n: int = 12,
    seed: int = 0,
    weights: Optional[Sequence[float]] = None,
    temperature: float = 1.0,
    min_p: float = 0.05,
) -> Dict[str, Any]:
    """Quorum/consensus decoding across a redundant transformer ring with fault isolation.

    Filters out models with non-finite weights or mismatched vocabularies,
    computes per-step token distributions across all healthy members, tracks
    top-1 token agreement (quorum ratio), and dynamically downweights members
    whose step logits are high-entropy or non-finite.
    """
    import math
    import random
    from skeleton.cortex.attn import sample_logits, softmax
    from skeleton.cortex.transformer import UNK, KVCache

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    candidates = [m for m in models if m is not None]
    if not candidates:
        return {"text": "", "healthy_models": 0, "quorum_agreement": 0.0, "degraded_models": 0}

    primary_itos = list(getattr(candidates[0], "itos", ()))
    healthy: List[Any] = []
    healthy_weights: List[float] = []
    degraded = 0
    for idx, m in enumerate(candidates):
        if list(getattr(m, "itos", ())) != primary_itos:
            degraded += 1
            continue
        if hasattr(m, "validate_finite_weights"):
            try:
                if not m.validate_finite_weights().get("healthy", False):
                    if hasattr(m, "restore_from_standby"):
                        m.restore_from_standby()
                    if not m.validate_finite_weights().get("healthy", False):
                        degraded += 1
                        continue
            except Exception:
                degraded += 1
                continue
        healthy.append(m)
        w = float(weights[idx]) if (weights is not None and idx < len(weights)) else 1.0
        healthy_weights.append(max(1e-6, w))

    if not healthy:
        raise RuntimeError("no healthy transformers available in redundant consensus ring")

    w_sum = sum(healthy_weights)
    base_weights = [w / w_sum for w in healthy_weights]
    lead = healthy[0]
    ids = list(lead._ids(prefix or "")) or [int(getattr(lead, "unk", 0))]
    caches = [
        KVCache(int(m.n_layers), int(m.ctx))
        if (hasattr(m, "_logits_window") and not getattr(m, "use_mod", False))
        else None
        for m in healthy
    ]
    vocab = int(getattr(lead, "V", len(primary_itos)))
    rng = random.Random(int(seed) & 0xFFFFFFFF)
    generated: List[int] = []
    agreements: List[float] = []
    step_failovers = 0

    for _ in range(n):
        step_probs: List[List[float]] = []
        step_w: List[float] = []
        top1_votes: Dict[int, int] = {}
        for m_idx, model in enumerate(healthy):
            ctx = int(getattr(model, "ctx", 6) or 6)
            window = [int(t) for t in ids][-ctx:] or [0]
            cache = caches[m_idx]
            try:
                logits = (
                    list(model._logits_window(window, cache))
                    if cache is not None
                    else list(model._logits(window))
                )
                if not all(math.isfinite(x) for x in logits):
                    step_failovers += 1
                    continue
                probs = softmax(logits)
                entropy = -sum(p * math.log(max(p, 1e-12)) for p in probs)
                conf_scale = 1.0 / (1.0 + max(0.0, entropy) * 0.25)
                step_probs.append(probs)
                step_w.append(base_weights[m_idx] * conf_scale)
                top_tok = max(range(vocab), key=lambda i: probs[i])
                top1_votes[top_tok] = top1_votes.get(top_tok, 0) + 1
            except Exception:
                step_failovers += 1
                continue

        if not step_probs:
            raise RuntimeError("all redundant transformers failed during step decode")

        sw_total = sum(step_w) or 1.0
        fused = [0.0] * vocab
        for probs, w in zip(step_probs, step_w):
            nw = w / sw_total
            for v in range(vocab):
                fused[v] += nw * probs[v]
        fused_logits = [math.log(max(p, 1e-12)) for p in fused]
        nxt = int(
            sample_logits(
                fused_logits,
                rng,
                temperature=temperature,
                min_p=min_p,
            )
        )
        ids.append(nxt)
        generated.append(nxt)
        max_vote = max(top1_votes.values()) if top1_votes else 1
        agreements.append(max_vote / max(1, len(step_probs)))

    text = " ".join(
        primary_itos[i] if 0 <= i < len(primary_itos) else UNK
        for i in generated
    )
    return {
        "text": text,
        "token_ids": generated,
        "healthy_models": len(healthy),
        "degraded_models": degraded,
        "step_failovers": step_failovers,
        "quorum_agreement": round(sum(agreements) / max(1, len(agreements)), 4),
    }
