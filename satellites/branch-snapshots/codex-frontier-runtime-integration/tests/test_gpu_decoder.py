"""Tests for GPU decoder prior.

Covers patch decoding, grid decoding, prior application, and stats.
"""
from __future__ import annotations

import pytest

from skeleton.intelligence.gpu_decoder_prior import DecodedPatch, GPUDecoderPrior


class TestDecodedPatch:
    def test_patch_creation(self):
        patch = DecodedPatch(x=0, y=0, w=32, h=32, latent=[0.1] * 64, confidence=0.8)
        assert patch.x == 0
        assert patch.confidence == 0.8

    def test_patch_to_dict(self):
        patch = DecodedPatch(x=0, y=0, w=32, h=32, latent=[0.1] * 64, confidence=0.8)
        d = patch.to_dict()
        assert d["confidence"] == 0.8
        assert d["w"] == 32


class TestGPUDecoderPrior:
    def test_decoder_creation(self):
        decoder = GPUDecoderPrior(patch_size=16, latent_dim=32)
        assert decoder.patch_size == 16
        assert decoder.latent_dim == 32

    def test_decode_patch(self):
        decoder = GPUDecoderPrior()
        patch = decoder.decode_patch([0.1] * 64, x=0, y=0)
        assert patch.w == 32  # warp-aligned
        assert patch.confidence > 0

    def test_decode_patch_with_prior(self):
        decoder = GPUDecoderPrior()
        decoder.set_prior("high_quality", {"confidence_boost": 1.5})
        patch = decoder.decode_patch([0.1] * 64, x=0, y=0, prior_hints=["high_quality"])
        assert patch.confidence == 0.75  # 0.5 * 1.5 capped at 1.0

    def test_decode_grid(self):
        decoder = GPUDecoderPrior(patch_size=16)
        latents = [[0.1] * 64 for _ in range(4)]
        patches = decoder.decode_grid(latents, grid_w=2, grid_h=2)
        assert len(patches) == 4
        assert patches[0].x == 0
        assert patches[1].x == 16

    def test_stats(self):
        decoder = GPUDecoderPrior()
        decoder.decode_patch([0.1] * 64, x=0, y=0)
        decoder.decode_patch([0.1] * 64, x=32, y=0)
        stats = decoder.stats()
        assert stats["decode_count"] == 2
        assert stats["avg_ms"] >= 0

    def test_card(self):
        decoder = GPUDecoderPrior()
        card = decoder.card()
        assert card["kind"] == "gpu-decoder-prior-card"
        assert card["patch_size"] == 32
