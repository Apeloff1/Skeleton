"""Exact checkpoint-byte and native restoration memory regressions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import math
import random
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes, digest_json, ModelRuntimeError
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import (
    _canonical_digest_and_size, _envelope_size, _validate_checkpoint_with_size,
    _restore_complete_reference_graph, logical_bytes, make_checkpoint,
    portable_model_snapshot, restore_components, snapshot_digest, validate_checkpoint,
)
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock


def runtime(*, tied=False, rope=False, large=False):
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma", "delta", "shader", "renderer", "world"),
        dim=128 if large else 8, ctx=64, n_layers=2, d_ff=128 if large else 8,
        n_heads=2, norm="rms", ffn_kind="swiglu", seed=82,
        position_mode="rope" if rope else "learned_rope",
    )
    if tied:
        model.tie()
    return NativeLLMRuntime(model)


def repin(checkpoint):
    checkpoint["model_digest"] = snapshot_digest(checkpoint["model"])
    body = {k: v for k, v in checkpoint.items() if k != "digest"}
    checkpoint["digest"] = digest_json(body)
    return checkpoint


class CanonicalStreamingTests(unittest.TestCase):
    def test_numeric_blocks_and_mixed_unicode_match_canonical_encoder(self):
        rng = random.Random(19)
        value = {
            "z": {"ø": [rng.uniform(-1e40, 1e40) for _ in range(2200)],
                  "a": [None, False, True, -0.0, 1e-300, 1e300, 0, -7],
                  "b": [1] * 1023 + ["é", {"snow": "雪", "nested": (1, 2)}] + [False] * 1025},
            "a": ["embedded\nseparator", "quote\"", "\\", "🧊"],
        }
        raw = canonical_bytes(value)
        self.assertEqual(_canonical_digest_and_size(value), (sha256(raw).hexdigest(), len(raw)))

    def test_empty_and_boundary_runs(self):
        for count in (0, 1, 1023, 1024, 1025, 2048, 2049):
            value = {"values": [(-1.0 if i % 2 else -0.0) for i in range(count)]}
            raw = canonical_bytes(value)
            self.assertEqual(_canonical_digest_and_size(value),
                             (sha256(raw).hexdigest(), len(raw)))

    def test_unsupported_numbers_and_cycles_fail_closed(self):
        for bad in (float("nan"), float("inf"), float("-inf"), object()):
            with self.assertRaises(ModelRuntimeError):
                _canonical_digest_and_size({"x": [1, bad]})
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ModelRuntimeError):
            _canonical_digest_and_size(cycle)

    def test_streaming_size_cutoff_is_exact_at_multibyte_boundary(self):
        value = {"array": [1.0] * 2050, "unicode": "blåbær雪"}
        size = len(canonical_bytes(value))
        self.assertEqual(_canonical_digest_and_size(value, maximum=size)[1], size)
        with self.assertRaises(RuntimeContractError):
            _canonical_digest_and_size(value, maximum=size - 1)

    def test_actual_large_graph_digest_uses_exact_canonical_bytes(self):
        model = runtime(large=True).model
        snapshot = portable_model_snapshot(model)
        raw = canonical_bytes(snapshot)
        self.assertEqual(snapshot_digest(snapshot), sha256(raw).hexdigest())

    def test_envelope_sizing_counts_digest_and_delimiters(self):
        for body in ({"a": "雪"}, {"a": [1, 2.0], "z": {"b": "x"}}):
            digest = digest_json(body)
            self.assertEqual(_envelope_size(len(canonical_bytes(body)), digest),
                             len(canonical_bytes({**body, "digest": digest})))

    def test_actual_checkpoint_envelope_is_verified_once_for_size(self):
        rt = runtime()
        cp = rt.checkpoint()
        body, total = _validate_checkpoint_with_size(cp)
        self.assertEqual(total, len(canonical_bytes(cp)))
        self.assertEqual(body, validate_checkpoint(cp))
        self.assertNotIn("digest", body)
        self.assertEqual(snapshot_digest(body["model"]), rt.model_digest)


class DirectRestoreTests(unittest.TestCase):
    def test_complete_cpu_restore_skips_random_constructor_and_preserves_receipt(self):
        for tied, rope in ((False, False), (False, True), (True, True)):
            original = runtime(tied=tied, rope=rope)
            cp = original.checkpoint()
            with patch.object(TinyTransformer, "__init__", side_effect=AssertionError("redundant model allocation")), \
                 patch.object(TransformerBlock, "__init__", side_effect=AssertionError("redundant layer allocation")):
                restored = NativeLLMRuntime.restore(cp)
            self.assertEqual(restored.model_digest, original.model_digest)
            self.assertEqual(restored.checkpoint(), cp)
            self.assertEqual(restored.model.Wout is restored.model.E, tied)
            config = GenerationConfig(max_new_tokens=3, temperature=.65, seed=37)
            a = original.generate("alpha beta gamma", config)
            b = restored.generate("alpha beta gamma", config)
            self.assertEqual(a.generated_ids, b.generated_ids)
            self.assertEqual(a.replay_receipt, b.replay_receipt)

    def test_direct_and_legacy_graphs_are_exact_on_real_forward(self):
        original = runtime()
        cp = original.checkpoint()
        direct = _restore_complete_reference_graph(cp["model"])
        legacy = TinyTransformer.from_snapshot(dict(cp["model"]))
        self.assertEqual(portable_model_snapshot(direct), portable_model_snapshot(legacy))
        self.assertEqual(direct._logits([1, 2, 3]), legacy._logits([1, 2, 3]))

    def test_restored_graph_never_aliases_checkpoint_rows(self):
        original = runtime()
        cp = original.checkpoint()
        restored = NativeLLMRuntime.restore(cp)
        before = restored.model.E[1][0]
        cp["model"]["E"][1][0] += 1.0
        cp["model"]["layers"][0]["Wq"][0][0] += 1.0
        self.assertEqual(restored.model.E[1][0], before)
        restored.assert_model_unchanged()

    def test_low_budgets_fail_before_constructing_any_graph(self):
        for key in ("max_model_bytes", "max_checkpoint_bytes"):
            original = runtime()
            cp = deepcopy(original.checkpoint())
            cp["limits"][key] = 1
            repin(cp)
            with patch("skeleton.ai.model_runtime.runtime_checkpoint._restore_complete_reference_graph",
                       side_effect=AssertionError("allocated before resource admission")):
                with self.assertRaises(RuntimeContractError):
                    restore_components(cp)

    def test_invalid_policy_fails_before_constructing_any_graph(self):
        cp = deepcopy(runtime().checkpoint())
        cp["device_policy"]["requested"] = "invalid-device"
        repin(cp)
        with patch("skeleton.ai.model_runtime.runtime_checkpoint._restore_complete_reference_graph",
                   side_effect=AssertionError("allocated before policy admission")):
            with self.assertRaises(RuntimeContractError):
                restore_components(cp)

    def test_first_layer_alias_and_tied_weights_cannot_disagree_even_when_repinned(self):
        for field, tied in (("Wq", False), ("Wout", True)):
            cp = deepcopy(runtime(tied=tied).checkpoint())
            cp["model"][field][0][0] += 1.
            repin(cp)
            with self.assertRaises(RuntimeContractError):
                NativeLLMRuntime.restore(cp)

    def test_model_identity_is_checked_after_actual_restore(self):
        cp = deepcopy(runtime().checkpoint())
        cp["model"]["E"][1][0] = 1
        repin(cp)
        # JSON int 1 becomes canonical model float 1.0. Do not admit a
        # differently canonicalized executable graph as the pinned artifact.
        with self.assertRaisesRegex(RuntimeContractError, "restored graph differs"):
            NativeLLMRuntime.restore(cp)

    def test_runtime_does_not_keep_second_detached_graph(self):
        rt = runtime()
        self.assertNotIn("_model_snapshot", vars(rt))
        before = rt.model_digest
        rt.model.Wout[0][0] += .01
        with self.assertRaises(RuntimeContractError):
            rt.assert_model_unchanged()
        self.assertNotEqual(rt.refresh_model_identity(), before)
        self.assertNotIn("_model_snapshot", vars(rt))
        rt.assert_model_unchanged()


if __name__ == "__main__":
    unittest.main()
