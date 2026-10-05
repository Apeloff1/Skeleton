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


class GPUDecoderPrior:
    """Decoder that respects GPU memory layout and warp coherence."""

    def __init__(self, patch_size: int = 32, latent_dim: int = 64, warp_size: int = 32):
        self.patch_size = patch_size
        self.latent_dim = latent_dim
        self.warp_size = warp_size
        self._priors: Dict[str, Any] = {}
        self._decode_count = 0
        self._total_ms = 0.0

    def set_prior(self, name: str, prior: Dict[str, Any]) -> None:
        self._priors[name] = prior

    def decode_patch(self, latent: List[float], x: int, y: int, prior_hints: Optional[List[str]] = None) -> DecodedPatch:
        t0 = time.time()
        # Simulated decode: apply priors as multiplicative biases
        confidence = 0.5
        decoded: Dict[str, Any] = {"type": "generic"}
        for hint in (prior_hints or []):
            p = self._priors.get(hint)
            if p is None:
                continue
            confidence *= p.get("confidence_boost", 1.0)
            decoded["prior"] = hint
            decoded.update(p.get("output_shape", {}))
        # Warp-align dimensions
        aligned_w = ((self.patch_size + self.warp_size - 1) // self.warp_size) * self.warp_size
        aligned_h = self.patch_size
        dt = (time.time() - t0) * 1000.0
        self._decode_count += 1
        self._total_ms += dt
        return DecodedPatch(
            x=x, y=y, w=aligned_w, h=aligned_h,
            latent=latent,
            confidence=min(1.0, confidence),
            decoded=decoded,
        )

    def decode_grid(self, latents: List[List[float]], grid_w: int, grid_h: int, prior_hints: Optional[List[str]] = None) -> List[DecodedPatch]:
        patches = []
        idx = 0
        for gy in range(grid_h):
            for gx in range(grid_w):
                if idx >= len(latents):
                    break
                patch = self.decode_patch(latents[idx], gx * self.patch_size, gy * self.patch_size, prior_hints)
                patches.append(patch)
                idx += 1
        return patches

    def stats(self) -> Dict[str, Any]:
        return {
            "decode_count": self._decode_count,
            "avg_ms": round(self._total_ms / max(1, self._decode_count), 4),
            "patch_size": self.patch_size,
            "latent_dim": self.latent_dim,
            "warp_size": self.warp_size,
        }

    def card(self) -> Dict[str, Any]:
        return {"kind": "gpu-decoder-prior-card", **self.stats(), "stored_prose": 0}
