"""Tests for parametric LoRA write-back."""
from __future__ import annotations

import pytest

from skeleton.intelligence.parametric_lora import LoRALayer, ParametricLoRAWriteBack


class TestLoRALayer:
    def test_to_dict(self):
        layer = LoRALayer(
            name="test",
            rank=4,
            alpha=8.0,
            lora_A=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5], [0.0, 0.0]],
            lora_B=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        )
        d = layer.to_dict()
        assert d["name"] == "test"
        assert d["rank"] == 4
        assert d["A_shape"] == [4, 2]
        assert d["B_shape"] == [2, 4]

    def test_effective_weight_shape(self):
        layer = LoRALayer(
            name="test",
            rank=2,
            alpha=4.0,
            lora_A=[[1.0, 0.0], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.0, 1.0]],
        )
        delta = layer.effective_weight()
        assert len(delta) == 2
        assert len(delta[0]) == 2


class TestParametricLoRAWriteBack:
    def test_add_layer(self):
        lora = ParametricLoRAWriteBack()
        layer = lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.0], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.0, 1.0]],
        )
        assert layer.name == "l1"
        assert "l1" in lora._layers

    def test_prune_rank(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
            lora_B=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            rank=3,
        )
        pruned = lora.prune_rank("l1", 2)
        assert pruned.rank == 2
        assert len(pruned.lora_A) == 2

    def test_prune_rank_no_change(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.0], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.0, 1.0]],
            rank=2,
        )
        pruned = lora.prune_rank("l1", 4)
        assert pruned.rank == 2

    def test_magnitude_gate(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.00001], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.00001, 1.0]],
        )
        pruned = lora.magnitude_gate("l1", threshold=1e-4)
        assert pruned > 0

    def test_merge_into_base(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.0], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.0, 1.0]],
            rank=2,
            alpha=2.0,
        )
        base = {"l1": [[0.0, 0.0], [0.0, 0.0]]}
        merged = lora.merge_into_base(base)
        assert "l1" in merged
        # Delta should be non-zero
        assert any(v != 0.0 for row in merged["l1"] for v in row)

    def test_merge_skips_frozen(self):
        lora = ParametricLoRAWriteBack()
        layer = lora.add_layer(
            "l1",
            lora_A=[[1.0, 0.0], [0.0, 1.0]],
            lora_B=[[1.0, 0.0], [0.0, 1.0]],
        )
        layer.frozen = True
        base = {"l1": [[1.0, 2.0], [3.0, 4.0]]}
        merged = lora.merge_into_base(base)
        assert merged["l1"] == [[1.0, 2.0], [3.0, 4.0]]

    def test_checkpoint(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer("l1", lora_A=[[1.0]], lora_B=[[1.0]])
        cp = lora.checkpoint(tag="test")
        assert cp["tag"] == "test"
        assert cp["layer_count"] == 1

    def test_card(self):
        lora = ParametricLoRAWriteBack()
        lora.add_layer("l1", lora_A=[[1.0, 0.0], [0.0, 1.0]], lora_B=[[1.0, 0.0], [0.0, 1.0]])
        card = lora.card()
        assert card["kind"] == "parametric-lora-card"
        assert card["layers"] == 1
        assert card["total_params"] == 8  # 2*2 + 2*2

    def test_save_load_roundtrip(self, tmp_path):
        lora = ParametricLoRAWriteBack(base_dim=512, default_rank=4, default_alpha=8.0)
        lora.add_layer("l1", lora_A=[[1.0]], lora_B=[[1.0]])
        path = str(tmp_path / "lora.json")
        lora.save(path)
        lora2 = ParametricLoRAWriteBack()
        lora2.load(path)
        assert lora2.base_dim == 512
        assert lora2.default_rank == 4
        assert lora2.default_alpha == 8.0
