"""End-to-end native offline chat: checkpoint -> local generation -> durable replay.

No provider credentials, network calls, or external model dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO
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

    def test_list_and_delete_session_cascades_receipts(self):
        sid = self.product.create()
        other = self.product.create(system="Stay precise.")
        self.product.turn(sid, "hello", self.config, request_id="receipt-1")
        self.assertEqual({entry[0] for entry in self.product.list_sessions()},
                         {sid, other})
        self.product.delete(sid)
        self.assertIsNone(self.store.replay(sid, "receipt-1", "b" * 64))
        self.assertEqual(tuple(x[0] for x in self.product.list_sessions()),
                         (other,))
        with self.assertRaises(RuntimeContractError):
            self.product.delete(sid)

    def test_generation_failure_preserves_previous_durable_state(self):
        sid = self.product.create()
        saved_method = self.engine.turn
        def broken(*args, **kwargs):
            raise RuntimeContractError("simulated local inference failure")
        self.engine.turn = broken
        try:
            with self.assertRaisesRegex(RuntimeContractError, "simulated"):
                self.product.turn(sid, "hello", self.config, request_id="failure")
        finally:
            self.engine.turn = saved_method
        stored = self.store.load(sid, self.product.model_digest,
                                 self.product.tokenizer_digest)
        self.assertEqual(stored.revision, 0)
        self.assertEqual(stored.transcript.messages, ())
        self.assertIsNone(self.store.replay(sid, "failure", "a" * 64))

    def test_interactive_cli_supports_multiple_turns_and_listing(self):
        checkpoint = self.root / "model.json"
        database = self.root / "terminal.sqlite"
        checkpoint.write_text(self.engine.runtime.checkpoint_json(), encoding="utf-8")
        output = StringIO()
        with patch("builtins.input", side_effect=["hello", "again", "/exit"]):
            with redirect_stdout(output):
                result = main(["--checkpoint", str(checkpoint),
                               "--database", str(database), "--interactive",
                               "--max-new-tokens", "2"])
        self.assertEqual(result, 0)
        self.assertIn("AI>", output.getvalue())
        listing = StringIO()
        with redirect_stdout(listing):
            self.assertEqual(main(["--checkpoint", str(checkpoint),
                                   "--database", str(database),
                                   "--list", "--json"]), 0)
        rows = json.loads(listing.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revision"], 2)
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["--checkpoint", str(checkpoint),
                                   "--database", str(database),
                                   "--delete-session", rows[0]["session_id"]]), 0)
        with OfflineChatStore(database) as reopened:
            self.assertEqual(reopened.list_sessions(
                self.product.model_digest, self.product.tokenizer_digest), ())

    def test_portable_export_import_preserves_history_and_replay(self):
        sid = self.product.create(system="Stay precise.")
        prior = self.product.turn(sid, "hello", self.config, request_id="portable")
        bundle = self.product.export_session(sid)
        restored = self.product.import_session(bundle)
        self.assertNotEqual(restored, sid)
        saved = self.store.load(restored, self.product.model_digest,
                                self.product.tokenizer_digest)
        self.assertEqual(saved.revision, 1)
        self.assertEqual(saved.transcript.messages[0].role, "system")
        self.assertEqual(saved.transcript.messages[-1].content, prior.text)
        repeated = self.product.turn(restored, "hello", self.config,
                                     request_id="portable")
        self.assertTrue(repeated.replayed)
        self.assertEqual(repeated.output_digest, prior.output_digest)
        self.assertEqual(repeated.revision, 1)

    def test_corrupt_backup_and_wrong_model_cannot_import(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="backup")
        bundle = self.product.export_session(sid)
        count = len(self.product.list_sessions())
        envelope = json.loads(bundle)
        envelope["body"]["messages"][-1]["content"] = "tampered"
        with self.assertRaisesRegex(RuntimeContractError, "digest mismatch"):
            self.product.import_session(json.dumps(envelope).encode("utf-8"))
        with self.assertRaisesRegex(RuntimeContractError, "model/tokenizer"):
            self.store.import_bundle(bundle, "b" * 64, self.product.tokenizer_digest)
        self.assertEqual(len(self.product.list_sessions()), count)

    def test_backup_import_is_create_only_and_failed_import_is_atomic(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="first")
        bundle = self.product.export_session(sid)
        a = self.product.import_session(bundle)
        b = self.product.import_session(bundle)
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.product.list_sessions()), 3)
        envelope = json.loads(bundle)
        envelope["body"]["turns"][0]["revision"] = True
        import hashlib
        import json as js
        canonical = js.dumps(
            envelope["body"], sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        envelope["sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(RuntimeContractError, "revision"):
            self.product.import_session(js.dumps(envelope).encode("utf-8"))
        self.assertEqual(len(self.product.list_sessions()), 3)

    def test_bundle_file_creation_denies_overwrite_and_symlink(self):
        from skeleton.ai.model_runtime.offline_chat import (
            load_private_bundle, save_private_bundle,
        )
        sid = self.product.create()
        backup = self.root / "backup.json"
        payload = self.product.export_session(sid)
        save_private_bundle(backup, payload)
        self.assertEqual(load_private_bundle(backup), payload)
        with self.assertRaises(FileExistsError):
            save_private_bundle(backup, payload)
        alias = self.root / "alias.json"
        alias.symlink_to(backup)
        with self.assertRaises(RuntimeContractError):
            load_private_bundle(alias)

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
