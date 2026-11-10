"""Regression tests for bounded native token-window collection."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.tokenization import (
    TokenWindow,
    TokenizerContractError,
    batch_token_windows,
)


class BoundedTokenBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = TokenWindow(0, 1, (1,), "a" * 64)

    def test_finite_batches_preserve_accounting(self) -> None:
        batches = batch_token_windows(
            iter((self.window, self.window)), max_batch_size=1, max_tokens_per_batch=2
        )
        self.assertEqual([batch.total_tokens for batch in batches], [1, 1])

    def test_unbounded_source_rejected_before_retaining_more_windows(self) -> None:
        with patch("skeleton.ai.model_runtime.tokenization.MAX_TEXT_CHUNKS", 2):
            with self.assertRaisesRegex(TokenizerContractError, "bounded runtime capacity"):
                batch_token_windows(
                    (self.window for _ in range(3)),
                    max_batch_size=1,
                    max_tokens_per_batch=2,
                )

    def test_total_token_capacity_is_independent_of_batch_size(self) -> None:
        with patch("skeleton.ai.model_runtime.tokenization.MAX_TOKENS", 2):
            with self.assertRaisesRegex(TokenizerContractError, "bounded runtime capacity"):
                batch_token_windows(
                    (self.window for _ in range(3)),
                    max_batch_size=1,
                    max_tokens_per_batch=2,
                )


if __name__ == "__main__":
    unittest.main()
