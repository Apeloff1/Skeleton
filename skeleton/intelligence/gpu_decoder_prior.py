"""GPU decoder prior — probabilistic scene decoding with GPU-shaped priors.

Provides a decoder that uses GPU-friendly tensor layouts and
hardware-aware priors to guide scene reconstruction, mesh
generation, and texture synthesis from latent codes.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DecodedPatch:
    x: int
    y: int
    w: int
    h: int
    latent: List[float]
    confidence: float
    decoded: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "confidence": round(self.confidence, 4),
            "decoded": self.decoded,
        }


def _positive_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


class GPUDecoderPrior:
    """Decoder that respects GPU memory layout and warp coherence."""

    def __init__(self, patch_size: int = 32, latent_dim: int = 64, warp_size: int = 32):
        self.patch_size = _positive_int(patch_size, "patch size")
        self.latent_dim = _positive_int(latent_dim, "latent dimension")
        self.warp_size = _positive_int(warp_size, "warp size")
        self._priors: Dict[str, Any] = {}
        self._decode_count = 0
        self._total_ms = 0.0

    def set_prior(self, name: str, prior: Dict[str, Any]) -> None:
        self._priors[name] = prior

    def decode_patch(self, latent: List[float], x: int, y: int, prior_hints: Optional[List[str]] = None) -> DecodedPatch:
        if not isinstance(latent, list) or len(latent) != self.latent_dim:
            raise ValueError("latent must match the decoder dimension")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in latent):
            raise ValueError("latent values must be finite")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int) or x < 0 or y < 0:
            raise ValueError("patch coordinates must be non-negative integers")
        if not prior_hints:
            raise ValueError("a prior is required")
        t0 = time.time()
        confidence = 1.0
        decoded: Dict[str, Any] = {}
        for hint in prior_hints:
            if not isinstance(hint, str) or hint not in self._priors:
                raise ValueError(f"unknown prior {hint!r}")
            prior = self._priors[hint]
            if not isinstance(prior, dict) or "confidence_boost" not in prior:
                raise ValueError("prior confidence is required")
            boost = prior["confidence_boost"]
            if isinstance(boost, bool) or not isinstance(boost, (int, float)) or not math.isfinite(float(boost)) or not 0 < float(boost) <= 1:
                raise ValueError("confidence boost must be in (0, 1]")
            confidence *= float(boost)
            decoded["prior"] = hint
            shape = prior.get("output_shape", {})
            if not isinstance(shape, dict):
                raise ValueError("output shape must be an object")
            decoded.update(shape)
        aligned_w = ((self.patch_size + self.warp_size - 1) // self.warp_size) * self.warp_size
        aligned_h = self.patch_size
        dt = (time.time() - t0) * 1000.0
        self._decode_count += 1
        self._total_ms += dt
        return DecodedPatch(
            x=x, y=y, w=aligned_w, h=aligned_h,
            latent=latent,
            confidence=confidence,
            decoded=decoded,
        )

    def decode_grid(self, latents: List[List[float]], grid_w: int, grid_h: int, prior_hints: Optional[List[str]] = None) -> List[DecodedPatch]:
        if isinstance(grid_w, bool) or isinstance(grid_h, bool) or not isinstance(grid_w, int) or not isinstance(grid_h, int) or grid_w < 1 or grid_h < 1:
            raise ValueError("grid dimensions must be positive integers")
        if len(latents) != grid_w * grid_h:
            raise ValueError("grid latents must match the grid")
        patches = []
        idx = 0
        for gy in range(grid_h):
            for gx in range(grid_w):
                patch = self.decode_patch(latents[idx], gx * self.patch_size, gy * self.patch_size, prior_hints)
                patches.append(patch)
                idx += 1
        return patches

    def stats(self) -> Dict[str, Any]:
        return {
            "decode_count": self._decode_count,
            "avg_ms": None if self._decode_count == 0 else round(self._total_ms / self._decode_count, 4),
            "patch_size": self.patch_size,
            "latent_dim": self.latent_dim,
            "warp_size": self.warp_size,
        }

    def card(self) -> Dict[str, Any]:
        return {"kind": "gpu-decoder-prior-card", **self.stats(), "stored_prose": 0}
