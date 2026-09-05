"""Tests for GPU decoder prior."""
from __future__ import annotations

import pytest

from skeleton.intelligence.gpu_decoder_prior import DecodedPatch, GPUDecoderPrior


class TestDecodedPatch:
    def test_to_dict(self):
        p = DecodedPatch(x=0, y=0, w=32, h=32, latent=[1.0], confidence=0.8, decoded={"type": "mesh"})
        d = p.to_dict()
        assert d["x"] == 0
        assert d["confidence"] == 0.8
        assert d["decoded"]["type"] == "mesh"


class TestGPUDecoderPrior:
    def test_decode_patch(self):
        decoder = GPUDecoderPrior(patch_size=32, latent_dim=64)
        patch = decoder.decode_patch([1.0] * 64, 0, 0)
        assert patch.x == 0
        assert patch.y == 0
        assert patch.w == 32
        assert patch.h == 32
        assert patch.confidence > 0

    def test_decode_patch_with_prior(self):
        decoder = GPUDecoderPrior(patch_size=32, latent_dim=64)
        decoder.set_prior("mesh", {"confidence_boost": 1.5, "output_shape": {"type": "mesh"}})
        patch = decoder.decode_patch([1.0] * 64, 0, 0, prior_hints=["mesh"])
        assert patch.confidence > 0.5
        assert patch.decoded["type"] == "mesh"

    def test_decode_grid(self):
        decoder = GPUDecoderPrior(patch_size=32, latent_dim=64)
        latents = [[1.0] * 64 for _ in range(4)]
        patches = decoder.decode_grid(latents, 2, 2)
        assert len(patches) == 4
        assert patches[0].x == 0
        assert patches[1].x == 32

    def test_warp_alignment(self):
        decoder = GPUDecoderPrior(patch_size=30, warp_size=32)
        patch = decoder.decode_patch([1.0], 0, 0)
        # Should be aligned to warp_size
        assert patch.w == 32  # ((30+31)//32)*32

    def test_stats(self):
        decoder = GPUDecoderPrior()
        decoder.decode_patch([1.0], 0, 0)
        stats = decoder.stats()
        assert stats["decode_count"] == 1
        assert stats["avg_ms"] >= 0

    def test_card(self):
        decoder = GPUDecoderPrior()
        card = decoder.card()
        assert card["kind"] == "gpu-decoder-prior-card"
        assert card["patch_size"] == 32
