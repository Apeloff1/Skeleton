"""Opt-in game-production Jeeves model capacity profiles.

The default legacy profile is unchanged for every existing install.
Profiles apply only to the *newly constructed model* before an existing
SKELETON_OWN checkpoint is restored. They do not rewrite a serving checkpoint
or magically scale trained weights; an explicit new production initialization
and governed training plan are needed to adopt a larger architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Iterable, Any


@dataclass(frozen=True)
class ModelCapacityProfile:
    name: str
    backend: str
    dim: int
    context: int
    layers: int
    heads: int
    feedforward: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "backend": self.backend,
            "dim": self.dim, "context": self.context,
            "layers": self.layers, "heads": self.heads,
            "feedforward": self.feedforward,
        }


PROFILES: dict[str, ModelCapacityProfile] = {
    "legacy": ModelCapacityProfile("legacy", "native", 8, 8, 2, 2, 32),
    "mobile": ModelCapacityProfile("mobile", "torch-stack", 32, 64, 2, 4, 128),
    "desktop": ModelCapacityProfile("desktop", "torch-stack", 128, 128, 4, 4, 512),
    "workstation": ModelCapacityProfile("workstation", "torch-stack", 256, 256, 6, 8, 1024),
}


def configured_profile() -> ModelCapacityProfile:
    raw = os.environ.get("SKELETON_JEEVES_PROFILE", "legacy").strip().lower()
    if raw not in PROFILES:
        raise ValueError(
            "unsupported SKELETON_JEEVES_PROFILE; use legacy, mobile, desktop or workstation"
        )
    return PROFILES[raw]


def _torch_device() -> str:
    requested = os.environ.get("SKELETON_JEEVES_DEVICE", "auto").strip().lower()
    if requested not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError("SKELETON_JEEVES_DEVICE must be auto, cpu, cuda or mps")
    import torch
    cuda = torch.cuda.is_available()
    mps = bool(
        getattr(torch.backends, "mps", None) is not None
        and torch.backends.mps.is_available()
    )
    if requested == "auto":
        return "cuda" if cuda else "mps" if mps else "cpu"
    if requested == "cuda" and not cuda:
        raise RuntimeError("requested CUDA device unavailable; refusing silent CPU fallback")
    if requested == "mps" and not mps:
        raise RuntimeError("requested Apple MPS device unavailable; refusing silent CPU fallback")
    return requested


def build_initial_speaking_model(
    *, vocab: Iterable[str], seed: int = 19,
) -> Any:
    """Construct the configured INITIAL model, not an implied production upgrade."""
    spec = configured_profile()
    if spec.name == "legacy":
        from skeleton.cortex.device import attach_lm
        return attach_lm(
            vocab=vocab,
            dim=spec.dim, ctx=spec.context, seed=seed,
            n_heads=spec.heads, n_layers=spec.layers,
            d_ff=spec.feedforward, device="auto",
        )
    try:
        from skeleton.cortex.torch_lm import TorchTransformer
        actual_device = _torch_device()
    except ImportError as exc:
        raise RuntimeError(
            "nonlegacy Jeeves profile requires installed PyTorch; no smaller-model fallback"
        ) from exc
    return TorchTransformer(
        vocab=vocab, dim=spec.dim, ctx=spec.context,
        seed=seed, n_heads=spec.heads, n_layers=spec.layers,
        d_ff=spec.feedforward, device=actual_device,
    )


__all__ = ["ModelCapacityProfile", "PROFILES", "configured_profile", "build_initial_speaking_model"]
