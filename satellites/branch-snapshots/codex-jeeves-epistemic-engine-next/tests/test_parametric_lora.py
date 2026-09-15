"""Tests for parametric LoRA write-back.

Covers layer creation, effective weight computation, rank pruning,
magnitude gating, checkpointing, and serialization.
"""
from __future__ import annotations

import pytest

from skeleton.intelligence.parametric_lora import LoRALayer, ParametricLoRAWriteBack


class TestLoRALayer:
    def test_layer_creation(self):
        A = [[0.1, 0.2], [0.3, 0.4]]
        B = [[0.5, 0.6], [0.7, 0.8]]
        layer = LoRALayer(name="test", rank=2, alpha=4.0, lora_A=A, lora_B=B)
        assert layer.name == "test"
        assert layer.rank == 2

    def test_effective_weight(self):
        A = [[1.0, 0.0], [0.0, 1.0]]
        B = [[1.0, 0.0], [0.0, 1.0]]
        layer = LoRALayer(name="test", rank=2, alpha=2.0, lora_A=A, lora_B=B)
        delta = layer.effective_weight()
        # alpha/rank = 1.0, so delta = B @ A = identity
        assert abs(delta[0][0] - 1.0) < 0.001
        assert abs(delta[1][1] - 1.0) < 0.001

    def test_to_dict(self):
        A = [[0.1, 0.2], [0.3, 0.4]]
        B = [[0.5, 0.6], [0.7, 0.8]]
        layer = LoRALayer(name="test", rank=2, alpha=4.0, lora_A=A, lora_B=B)
        d = layer.to_dict()
        assert d["name"] == "test"
        assert d["A_shape"] == [2, 2]


class TestParametricLoRAWriteBack:
    def test_creation(self):
        lora = ParametricLoRAWriteBack(base_dim=512, default_rank=4)
        assert lora.base_dim == 512
        assert lora.default_rank == 4

    def test_add_layer(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(8)]
        B = [[0.1] * 8 for _ in range(768)]
        layer = lora.add_layer("layer1", A, B)
        assert layer.name == "layer1"
        assert len(lora._layers) == 1

    def test_prune_rank(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(8)]
        B = [[0.1] * 8 for _ in range(768)]
        lora.add_layer("layer1", A, B)
        pruned = lora.prune_rank("layer1", 4)
        assert pruned.rank == 4
        assert len(pruned.lora_A) == 4

    def test_prune_rank_no_change(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(4)]
        B = [[0.1] * 4 for _ in range(768)]
        lora.add_layer("layer1", A, B)
        pruned = lora.prune_rank("layer1", 8)
        assert pruned.rank == 4  # no change

    def test_magnitude_gate(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.0001, 1.0], [0.0001, 1.0]]
        B = [[0.0001, 1.0], [0.0001, 1.0]]
        lora.add_layer("layer1", A, B)
        count = lora.magnitude_gate("layer1", threshold=0.01)
        assert count > 0
        # Small values should be zeroed
        assert lora._layers["layer1"].lora_A[0][0] == 0.0

    def test_merge_into_base(self):
        lora = ParametricLoRAWriteBack()
        A = [[1.0, 0.0], [0.0, 1.0]]
        B = [[1.0, 0.0], [0.0, 1.0]]
        lora.add_layer("layer1", A, B, rank=2, alpha=2.0)
        base = {"layer1": [[1.0, 0.0], [0.0, 1.0]]}
        merged = lora.merge_into_base(base)
        # base + delta = identity + identity = [[2, 0], [0, 2]]
        assert abs(merged["layer1"][0][0] - 2.0) < 0.001

    def test_checkpoint(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(8)]
        B = [[0.1] * 8 for _ in range(768)]
        lora.add_layer("layer1", A, B)
        cp = lora.checkpoint(tag="test")
        assert cp["tag"] == "test"
        assert cp["layer_count"] == 1
        assert len(lora._checkpoints) == 1

    def test_card(self):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(8)]
        B = [[0.1] * 8 for _ in range(768)]
        lora.add_layer("layer1", A, B)
        card = lora.card()
        assert card["kind"] == "parametric-lora-card"
        assert card["layers"] == 1
        assert card["total_params"] > 0

    def test_save_load_roundtrip(self, tmp_path):
        lora = ParametricLoRAWriteBack()
        A = [[0.1] * 768 for _ in range(8)]
        B = [[0.1] * 8 for _ in range(768)]
        lora.add_layer("layer1", A, B)
        path = str(tmp_path / "lora.json")
        lora.save(path)
        lora2 = ParametricLoRAWriteBack()
        lora2.load(path)
        assert lora2.base_dim == lora.base_dim
        assert lora2.default_rank == lora.default_rank
