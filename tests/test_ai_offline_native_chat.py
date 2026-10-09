"""End-to-end native offline chat: checkpoint -> local generation -> durable replay.

No provider credentials, network calls, or external model dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.offline_chat import (
    OfflineChatProduct, OfflineChatStore, load_offline_engine, main,
)
from skeleton.ai.model_runtime.runtime_contracts import (
    GenerationConfig, RuntimeContractError,
)


def _native() -> NativeChatEngine:
    # A deliberately untrained local transformer validates execution plumbing,
    # not response quality. Its prompt/context budget accommodates role frames.
    transformer = TinyTransformer(
        vocab=list(" abcdefghijklmnopqrstuvwxyz!?"), dim=8, ctx=256, seed=5
    )
    return NativeChatEngine(NativeLLMRuntime(transformer))


class OfflineNativeChatTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = OfflineChatStore(self.root / "chat.sqlite")
        self.addCleanup(lambda: self.store.close())
        self.engine = _native()
        self.product = OfflineChatProduct(self.engine, self.store)
        self.config = GenerationConfig(max_new_tokens=2, seed=2, top_k=1)

    def test_create_generate_and_reopen_durable_session(self):
        sid = self.product.create(system="Be precise.")
        first = self.product.turn(sid, "hello", self.config, request_id="turn-one")
        self.assertEqual(first.revision, 1)
        self.assertFalse(first.replayed)
        self.assertEqual(first.generated_tokens, 2)
        self.assertEqual(first.session_id, sid)
        loaded = self.store.load(sid, self.product.model_digest,
                                 self.product.tokenizer_digest)
        self.assertEqual(loaded.revision, 1)
        self.assertEqual(loaded.transcript.messages[-2].content, "hello")
        self.assertEqual(loaded.transcript.messages[-1].role, "assistant")
        self.store.close()
        self.store = OfflineChatStore(self.root / "chat.sqlite")
        self.product = OfflineChatProduct(self.engine, self.store)
        second = self.product.turn(sid, "next", self.config, request_id="turn-two")
        self.assertEqual(second.revision, 2)
        self.assertEqual(len(self.store.load(
            sid, self.product.model_digest, self.product.tokenizer_digest
        ).transcript.messages), 5)

    def test_retry_is_idempotent_across_restart(self):
        sid = self.product.create()
        first = self.product.turn(sid, "hello", self.config, request_id="same-key")
        again = self.product.turn(sid, "hello", self.config, request_id="same-key")
        self.assertTrue(again.replayed)
        self.assertEqual(again.text, first.text)
        self.assertEqual(again.output_digest, first.output_digest)
        self.assertEqual(again.revision, 1)
        self.assertEqual(self.store.load(sid, self.product.model_digest,
                                         self.product.tokenizer_digest).revision, 1)

    def test_replay_with_changed_content_or_configuration_is_rejected(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="stable")
        with self.assertRaisesRegex(RuntimeContractError, "request id reused"):
            self.product.turn(sid, "changed", self.config, request_id="stable")
        with self.assertRaisesRegex(RuntimeContractError, "request id reused"):
            self.product.turn(sid, "hello",
                              GenerationConfig(max_new_tokens=3, seed=2, top_k=1),
                              request_id="stable")

    def test_failed_or_unfittable_turn_does_not_commit(self):
        sid = self.product.create()
        with self.assertRaises(RuntimeContractError):
            self.product.turn(sid, "X" * 300000, self.config, request_id="oversized")
        self.assertEqual(self.store.load(sid, self.product.model_digest,
                                         self.product.tokenizer_digest).revision, 0)

    def test_stale_revision_is_denied(self):
        sid = self.product.create()
        before = self.store.load(sid, self.product.model_digest,
                                 self.product.tokenizer_digest)
        one = self.product.turn(sid, "hello", self.config, request_id="first")
        with self.assertRaisesRegex(RuntimeContractError, "revision conflict"):
            self.store.commit(
                session=before, request_id="second", request_digest="b" * 64,
                transcript=self.store.load(sid, self.product.model_digest,
                                           self.product.tokenizer_digest).transcript,
                text=one.text, output_digest=one.output_digest,
                prompt_tokens=1, generated_tokens=1,
            )
        self.assertEqual(self.store.load(sid, self.product.model_digest,
                                         self.product.tokenizer_digest).revision, 1)

    def test_session_is_bound_to_exact_model_and_tokenizer(self):
        sid = self.product.create()
        with self.assertRaisesRegex(RuntimeContractError, "different model"):
            self.store.load(sid, "a" * 64, self.product.tokenizer_digest)
        with self.assertRaisesRegex(RuntimeContractError, "different model"):
            self.store.load(sid, self.product.model_digest, "b" * 64)

    def test_integrity_checked_checkpoint_restores_with_no_provider(self):
        p = self.root / "model.json"
        p.write_text(self.engine.runtime.checkpoint_json(), encoding="utf-8")
        reopened = load_offline_engine(p)
        self.assertEqual(reopened.runtime.model_digest,
                         self.engine.runtime.model_digest)
        self.assertEqual(reopened.runtime.tokenizer.digest,
                         self.engine.runtime.tokenizer.digest)
        response = reopened.generate(
            self.store.load(self.product.create(), self.product.model_digest,
                            self.product.tokenizer_digest).transcript.append("user", "hello"),
            self.config,
        )
        self.assertEqual(len(response.generation.generated_ids), 2)

    def test_corrupt_checkpoint_is_rejected_before_inference(self):
        p = self.root / "model.json"
        checkpoint = json.loads(self.engine.runtime.checkpoint_json())
        checkpoint["model_digest"] = "0" * 64
        p.write_text(json.dumps(checkpoint), encoding="utf-8")
        with self.assertRaises(RuntimeContractError):
            load_offline_engine(p)

    def test_cli_real_local_inference_and_resume(self):
        p = self.root / "model.json"
        p.write_text(self.engine.runtime.checkpoint_json(), encoding="utf-8")
        self.assertEqual(main(["--checkpoint", str(p), "--database",
                               str(self.root / "cli.sqlite"), "--message",
                               "hello", "--max-new-tokens", "2", "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
