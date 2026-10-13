"""Native tokenization failures must never escape the runtime contract envelope."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import NativeLLMRuntime, GenerationConfig, RuntimeContractError
from skeleton.ai.model_runtime.tokenization import NativeTokenizer, StreamingTextFeed, TokenizerContractError


def model():
    return TinyTransformer(
        vocab=("alpha", "beta", "gamma", "delta"),
        dim=8, ctx=8, seed=47, n_heads=2, n_layers=2, d_ff=16,
    )


class TestTokenizerRuntimeErrorEnvelope(unittest.TestCase):
    def test_initial_admission_maps_tokenizer_failure(self):
        with patch("skeleton.ai.model_runtime.native_llm_runtime.NativeTokenizer",
                   side_effect=TokenizerContractError("bad vocabulary")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer admission failed") as ctx:
                NativeLLMRuntime(model())
        self.assertIsInstance(ctx.exception.__cause__, TokenizerContractError)

    def test_direct_encode_and_decode_map_tokenizer_failures(self):
        runtime = NativeLLMRuntime(model())
        with patch.object(runtime.tokenizer, "encode_sequence",
                          side_effect=TokenizerContractError("invalid token")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer encode failed") as ctx:
                runtime.encode("alpha")
        self.assertIsInstance(ctx.exception.__cause__, TokenizerContractError)
        with patch.object(runtime.tokenizer, "decode_ids",
                          side_effect=TokenizerContractError("invalid token")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer decode failed") as ctx:
                runtime.decode_ids([0])
        self.assertIsInstance(ctx.exception.__cause__, TokenizerContractError)

    def test_stream_preserves_prompt_admission_error(self):
        runtime = NativeLLMRuntime(model())
        with patch.object(runtime.tokenizer, "encode_sequence",
                          side_effect=TokenizerContractError("invalid prompt")):
            with self.assertRaisesRegex(RuntimeContractError, "prompt tokenization failed admission"):
                runtime.generate("alpha", GenerationConfig(max_new_tokens=1))

    def test_feed_finalization_maps_tokenizer_failure_for_all_entrypoints(self):
        runtime = NativeLLMRuntime(model())
        config = GenerationConfig(max_new_tokens=1)
        for operation in ("infer_feed", "stream_feed", "generate_feed"):
            with self.subTest(operation=operation):
                feed = StreamingTextFeed()
                feed.push("alpha")
                with patch.object(
                    feed, "finalize",
                    side_effect=TokenizerContractError("invalid feed identity"),
                ):
                    with self.assertRaisesRegex(
                        RuntimeContractError, "feed tokenization failed admission"
                    ) as ctx:
                        if operation == "infer_feed":
                            runtime.infer_feed(feed)
                        else:
                            getattr(runtime, operation)(feed, config)
                self.assertIsInstance(ctx.exception.__cause__, TokenizerContractError)

    def test_feed_entrypoints_reject_wrong_type_without_consumption(self):
        runtime = NativeLLMRuntime(model())
        for operation in ("infer_feed", "stream_feed", "generate_feed"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(RuntimeContractError, "StreamingTextFeed required"):
                    getattr(runtime, operation)(None)

    def test_checkpoint_and_restore_reject_tokenizer_contract_failure(self):
        runtime = NativeLLMRuntime(model())
        checkpoint = runtime.checkpoint()
        with patch.object(runtime.tokenizer, "assert_unchanged",
                          side_effect=TokenizerContractError("drift")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer changed before checkpoint"):
                runtime.checkpoint()
        with patch.object(NativeTokenizer, "assert_checkpoint_matches",
                          side_effect=TokenizerContractError("checkpoint mismatch")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer checkpoint identity mismatch"):
                NativeLLMRuntime.restore(checkpoint)

    def test_graph_inference_rejects_tokenizer_drift_as_runtime_error(self):
        runtime = NativeLLMRuntime(model())
        sequence = runtime.encode("alpha")
        with patch.object(runtime.tokenizer, "assert_unchanged",
                          side_effect=TokenizerContractError("drift")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer drift during inference"):
                runtime.infer_sequence(sequence)


if __name__ == "__main__":
    unittest.main()
