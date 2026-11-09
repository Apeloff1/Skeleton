"""Torch game-vocabulary growth and exact token-row restore contracts."""
from __future__ import annotations

import importlib.util
import unittest

from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError
from skeleton.ai.training.jeeves_torch_game_vocabulary import (
    expand_torch_game_words, planned_new_words,
)

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(TORCH_AVAILABLE, "Torch is optional, required for Torch vocabulary checks")
class JeevesTorchGameVocabularyTests(unittest.TestCase):
    def _new_model(self):
        from skeleton.cortex.torch_lm import TorchTransformer
        return TorchTransformer(
            vocab=("baseline", "quest", "agent"),
            dim=8, ctx=8, n_layers=1, n_heads=2, d_ff=16, device="cpu",
        )

    def test_preserves_pretrained_rows_and_attention(self) -> None:
        import torch
        model = self._new_model()
        old = {key: value.detach().clone() for key, value in model.net.state_dict().items()}
        original_ids = dict(model.stoi)
        docs = ("Build a playable branching survival quest with recoverable failure.",)
        missing = planned_new_words(model, docs)
        self.assertGreater(len(missing), 0)
        receipt = expand_torch_game_words(
            model, docs, expected_snapshot_digest="f" * 64,
        )
        self.assertEqual(receipt["new_tokens"], len(missing))
        self.assertTrue(receipt["pretrained_rows_preserved"])
        self.assertEqual(model.stoi["baseline"], original_ids["baseline"])
        self.assertTrue(torch.equal(
            model.net.E.weight[:len(original_ids)], old["E.weight"],
        ))
        self.assertTrue(torch.equal(
            model.net.out.weight[:len(original_ids)], old["out.weight"],
        ))
        self.assertTrue(torch.equal(
            model.net.out.bias[:len(original_ids)], old["out.bias"],
        ))
        self.assertTrue(all(
            torch.equal(model.net.state_dict()[name], value)
            for name, value in old.items()
            if name not in {"E.weight", "out.weight", "out.bias"}
        ))
        self.assertEqual(planned_new_words(model, docs), ())
        self.assertEqual(len(list(model._opt.param_groups[0]["params"])),
                         len(list(model.net.parameters())))

    def test_snapshot_restore_preserves_appended_token_order(self) -> None:
        from skeleton.cortex.torch_lm import TorchTransformer
        model = self._new_model()
        docs = ("A different scenic dialogue game movement.",)
        expand_torch_game_words(model, docs, expected_snapshot_digest="d" * 64)
        snapshot = model.snapshot()
        restored = TorchTransformer.from_snapshot(snapshot)
        self.assertEqual(restored.itos, model.itos)
        self.assertEqual(restored.stoi, model.stoi)
        self.assertEqual(restored.snapshot()["state"], snapshot["state"])
        self.assertEqual(restored._id("scenic"), model._id("scenic"))

    def test_no_unexpected_duplicate_or_missing_tokens(self) -> None:
        from skeleton.cortex.torch_lm import TorchTransformer
        model = self._new_model()
        saved = model.snapshot()
        bad = dict(saved)
        bad["itos"] = [saved["itos"][0]] * len(saved["itos"])
        with self.assertRaisesRegex(ValueError, "unique ordered"):
            TorchTransformer.from_snapshot(bad)
        bad = dict(saved)
        bad["state"] = {}
        with self.assertRaisesRegex(ValueError, "missing trained"):
            TorchTransformer.from_snapshot(bad)

    def test_growth_rejects_missing_parent_snapshot_digest(self) -> None:
        model = self._new_model()
        with self.assertRaisesRegex(ProductionCheckpointError, "digest"):
            expand_torch_game_words(
                model, ("game design quest",), expected_snapshot_digest="invalid",
            )


if __name__ == "__main__":
    unittest.main()
