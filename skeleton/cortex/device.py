"""Device harness — CPU always, CUDA when torch can see a GPU.

Never import torch at module load. GameForge CI is stdlib-only.
probe() is the truth: name, backend, cuda, gpu. attach_lm()
picks the fastest net that can actually run.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def probe() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "name": "cpu",
        "backend": "python",
        "torch": False,
        "cuda": False,
        "gpu": None,
        "count": 0,
    }
    try:
        import torch  # noqa: WPS433 — lazy, optional
    except Exception:
        return info
    info["torch"] = True
    info["backend"] = "torch"
    info["torch_version"] = str(getattr(torch, "__version__", ""))
    try:
        ok = bool(torch.cuda.is_available())
    except Exception:
        ok = False
    info["cuda"] = ok
    if ok:
        info["name"] = "cuda"
        info["count"] = int(torch.cuda.device_count())
        try:
            info["gpu"] = str(torch.cuda.get_device_name(0))
        except Exception:
            info["gpu"] = "cuda:0"
    return info


def resolve(device: str = "auto") -> Dict[str, Any]:
    p = probe()
    want = (device or "auto").lower()
    if want in {"gpu", "cuda"}:
        actual = "cuda" if p["cuda"] else "cpu"
        return {**p, "requested": "cuda", "actual": actual, "degraded": actual != "cuda"}
    if want == "auto":
        actual = p["name"]
        return {**p, "requested": "auto", "actual": actual, "degraded": False}
    return {**p, "requested": "cpu", "actual": "cpu", "degraded": False}


def attach_lm(
    vocab: Iterable[str] | None = None,
    *,
    dim: int = 8,
    ctx: int = 8,
    seed: int = 19,
    n_heads: int = 2,
    n_layers: int = 2,
    d_ff: int = 32,
    device: str = "auto",
):
    """Neo-scale LM. Torch stack on CUDA/CPU-torch; TinyTransformer otherwise."""
    from skeleton.cortex.transformer import TinyTransformer
    resolved = resolve(device)
    lm = TinyTransformer(
        vocab=vocab, dim=dim, ctx=ctx, seed=seed,
        n_heads=n_heads, n_layers=1 if resolved["backend"] == "python" else n_layers,
        d_ff=d_ff,
    )
    lm.to(resolved["actual"])
    if resolved["backend"] == "torch":
        try:
            from skeleton.cortex.torch_lm import TorchTransformer
            stacked = TorchTransformer(
                vocab=vocab, dim=dim, ctx=ctx, seed=seed,
                n_heads=n_heads, n_layers=n_layers, d_ff=d_ff,
                device=resolved["actual"],
            )
            stacked._tiny = lm
            return stacked
        except Exception:
            return lm
    return lm
