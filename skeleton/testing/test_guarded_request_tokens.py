"""Authoritative tokenizer-limit contract; test counter is not a production tokenizer."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.token_floor import NativeTokenFence
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

MODEL = "a" * 64
TOKENIZER = "b" * 64


class TestTokenFence(unittest.TestCase):
    def test_exact_native_counter_reserve(self):
        gate = NativeTokenFence(
            model_sha256=MODEL, tokenizer_sha256=TOKENIZER,
            counter=lambda value: len(value.split()), max_context=64,
        )
        result = gate.reserve(
            "one two three", model_sha256=MODEL,
            tokenizer_sha256=TOKENIZER, output_tokens=60, system_reserve=1,
        )
        self.assertEqual(result.available_margin, 0)
        self.assertEqual(result.prompt_tokens, 3)

    def test_bound_model_tokenizer(self):
        gate = NativeTokenFence(
            model_sha256=MODEL, tokenizer_sha256=TOKENIZER,
            counter=lambda value: len(value.split()), max_context=64,
        )
        for model, tokenizer in (("c" * 64, TOKENIZER), (MODEL, "d" * 64)):
            with self.subTest(model=model[:2], tokenizer=tokenizer[:2]), self.assertRaises(GateDenied):
                gate.reserve(
                    "one", model_sha256=model, tokenizer_sha256=tokenizer,
                    output_tokens=8,
                )

    def test_model_cannot_invent_count(self):
        for fake in (True, -1, 1.5, "5"):
            gate = NativeTokenFence(
                model_sha256=MODEL, tokenizer_sha256=TOKENIZER,
                counter=lambda _value, v=fake: v, max_context=64,
            )
            with self.subTest(fake=fake), self.assertRaises(GateDenied):
                gate.reserve(
                    "one", model_sha256=MODEL,
                    tokenizer_sha256=TOKENIZER, output_tokens=8,
                )

    def test_over_budget_refused(self):
        gate = NativeTokenFence(
            model_sha256=MODEL, tokenizer_sha256=TOKENIZER,
            counter=lambda value: len(value.split()), max_context=64,
        )
        with self.assertRaises(GateDenied):
            gate.reserve(
                "one two three", model_sha256=MODEL,
                tokenizer_sha256=TOKENIZER, output_tokens=64,
            )


if __name__ == "__main__":
    unittest.main()
