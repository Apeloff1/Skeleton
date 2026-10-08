"""Draft #3542: midstream feed must not close before a rejected tokenizer."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.tokenization import StreamingTextFeed, TokenizerContractError


class FeedRelease(unittest.TestCase):
    def test_wrong_tokenizer_does_not_close_or_drop_chunks(self) -> None:
        feed = StreamingTextFeed()
        feed.push("alpha")
        with self.assertRaises(TokenizerContractError):
            feed.finalize(object())
        self.assertFalse(feed.closed)
        self.assertEqual(feed.consume_text(), "alpha")
        self.assertEqual(feed._chunks, [])
        self.assertTrue(feed.closed)

    def test_identity_bind_rejects_drift_and_bad_digest(self) -> None:
        feed = StreamingTextFeed()
        feed.bind_identity("ab" * 32)
        with self.assertRaises(TokenizerContractError):
            feed.bind_identity("cd" * 32)
        with self.assertRaises(TokenizerContractError):
            StreamingTextFeed().bind_identity("ZZ" * 32)
        self.assertEqual(feed._bound_digest, "ab" * 32)


if __name__ == "__main__":
    unittest.main()
