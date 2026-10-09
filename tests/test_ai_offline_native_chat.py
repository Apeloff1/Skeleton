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
                transcript=before.transcript.append("user", "stale").append(
                    "assistant", one.text
                ),
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

    def test_signed_but_truncated_history_backup_is_rejected(self):
        import hashlib
        sid = self.product.create(system="Keep history.")
        self.product.turn(sid, "hello", self.config, request_id="first-history")
        self.product.turn(sid, "again", self.config, request_id="second-history")
        original = json.loads(self.product.export_session(sid))
        original["body"]["messages"] = (
            original["body"]["messages"][:1]
            + original["body"]["messages"][-2:]
        )
        canonical = json.dumps(original["body"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        original["sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(RuntimeContractError, "history is incomplete"):
            self.product.import_session(json.dumps(original).encode("utf-8"))

    def test_backup_checks_all_historical_assistant_receipts(self):
        import hashlib
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="first-record")
        self.product.turn(sid, "again", self.config, request_id="second-record")
        envelope = json.loads(self.product.export_session(sid))
        envelope["body"]["turns"][0]["text"] = "forged previous answer"
        canonical = json.dumps(envelope["body"], sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        envelope["sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(RuntimeContractError, "history/receipt mismatch"):
            self.product.import_session(json.dumps(envelope).encode("utf-8"))

    def test_deleted_historical_receipt_denies_resume_and_new_generation(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="first-receipt")
        self.product.turn(sid, "again", self.config, request_id="second-receipt")
        with self.store._transaction():
            self.store._db.execute(
                "DELETE FROM offline_turns WHERE session_id=? AND revision=1",
                (sid,),
            )
        with self.assertRaisesRegex(RuntimeContractError, "missing turn receipts"):
            self.store.load(sid, self.product.model_digest,
                            self.product.tokenizer_digest)
        with self.assertRaises(RuntimeContractError):
            self.product.turn(sid, "third", self.config, request_id="third-receipt")
        with self.store._lock:
            current = self.store._db.execute(
                "SELECT revision FROM offline_sessions WHERE session_id=?", (sid,),
            ).fetchone()
        self.assertEqual(current[0], 2)

    def test_modified_earlier_response_denies_corrupted_state(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="original")
        self.product.turn(sid, "again", self.config, request_id="second")
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_turns SET text=? WHERE session_id=? AND revision=1",
                ("forged-earlier-output", sid),
            )
        with self.assertRaisesRegex(RuntimeContractError, "history/receipt mismatch"):
            self.store.load(sid, self.product.model_digest,
                            self.product.tokenizer_digest)
        with self.assertRaises(RuntimeContractError):
            self.store.export_bundle(sid, self.product.model_digest,
                                     self.product.tokenizer_digest)

    def test_revision_forgery_cannot_create_orphaned_turns(self):
        sid = self.product.create()
        self.product.turn(sid, "hello", self.config, request_id="one")
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_sessions SET revision=? WHERE session_id=?",
                (2, sid),
            )
        with self.assertRaisesRegex(RuntimeContractError, "missing turn receipts"):
            self.store.load(sid, self.product.model_digest,
                            self.product.tokenizer_digest)

    def test_complete_history_capacity_rejected_before_model_inference(self):
        # Deterministically construct a valid, fully receipted 1,024-turn
        # conversation without spending CPU on 1,024 model generations.
        from skeleton.ai.model_runtime.chat_protocol import ChatMessage, ChatTranscript
        sid = self.product.create()
        messages = tuple(
            message
            for index in range(1024)
            for message in (
                ChatMessage("user", f"question-{index}"),
                ChatMessage("assistant", f"answer-{index}"),
            )
        )
        transcript = ChatTranscript(messages)
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_sessions SET revision=?, transcript_json=? WHERE session_id=?",
                (1024, transcript.to_json(), sid),
            )
            self.store._db.executemany(
                "INSERT INTO offline_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(sid, f"turn-{i}", "a" * 64, i + 1,
                  f"answer-{i}", "b" * 64, 3, 1)
                 for i in range(1024)],
            )
        self.assertEqual(self.store.load(
            sid, self.product.model_digest, self.product.tokenizer_digest
        ).revision, 1024)
        with patch.object(self.engine, "turn") as generate:
            with self.assertRaisesRegex(RuntimeContractError, "turn capacity"):
                self.product.turn(
                    sid, "one-more-question", self.config, request_id="excess"
                )
            generate.assert_not_called()
        self.assertEqual(self.store.load(
            sid, self.product.model_digest, self.product.tokenizer_digest
        ).revision, 1024)

    def test_same_revision_changed_prior_transcript_is_not_silently_overwritten(self):
        sid = self.product.create(system="original-system")
        snapshot = self.store.load(
            sid, self.product.model_digest, self.product.tokenizer_digest
        )
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_sessions SET transcript_json=? WHERE session_id=?",
                ('[{"role":"system","content":"substituted-context"}]', sid),
            )
        attempted = snapshot.transcript.append("user", "hello").append(
            "assistant", "stale-answer"
        )
        with self.assertRaisesRegex(RuntimeContractError, "revision conflict"):
            self.store.commit(
                session=snapshot, request_id="stale-context", request_digest="a" * 64,
                transcript=attempted, text="stale-answer", output_digest="b" * 64,
                prompt_tokens=2, generated_tokens=1,
            )
        current = self.store.load(
            sid, self.product.model_digest, self.product.tokenizer_digest
        )
        self.assertEqual(current.revision, 0)
        self.assertEqual(current.transcript.messages[0].content,
                         "substituted-context")

    def test_two_separate_sqlite_connections_commit_without_lost_updates(self):
        sid = self.product.create()
        with OfflineChatStore(self.root / "chat.sqlite") as other:
            initial = other.load(sid, self.product.model_digest,
                                 self.product.tokenizer_digest)
            self.product.turn(sid, "hello", self.config, request_id="first-writer")
            with self.assertRaisesRegex(RuntimeContractError, "revision conflict"):
                other.commit(
                    session=initial,
                    request_id="second-writer",
                    request_digest="a" * 64,
                    transcript=initial.transcript.append("user", "hello").append(
                        "assistant", "stale-answer"),
                    text="stale-answer", output_digest="b" * 64,
                    prompt_tokens=1, generated_tokens=1,
                )
            current = other.load(sid, self.product.model_digest,
                                 self.product.tokenizer_digest)
            self.assertEqual(current.revision, 1)
            self.assertEqual(current.transcript.messages[-2].content, "hello")

    def test_world_readable_wal_and_shm_sidecars_are_denied(self):
        import os
        if os.name == "nt":
            self.skipTest("POSIX SQLite journal privacy test")
        path = self.root / "sidecar.sqlite"
        with OfflineChatStore(path):
            pass
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = self.root / ("sidecar.sqlite" + suffix)
            sidecar.write_bytes(b"canary")
            sidecar.chmod(0o644)
            with self.assertRaisesRegex(RuntimeContractError, "owner-only permissions"):
                OfflineChatStore(path)
            sidecar.unlink()

    def test_sidecar_symlink_is_denied_before_sqlite_open(self):
        import os
        if os.name == "nt":
            self.skipTest("POSIX SQLite symlink privacy test")
        path = self.root / "private-main.sqlite"
        with OfflineChatStore(path):
            pass
        target = self.root / "secret-external.txt"
        target.write_text("unrelated sensitive content", encoding="utf-8")
        journal = self.root / "private-main.sqlite-wal"
        journal.symlink_to(target)
        with self.assertRaisesRegex(RuntimeContractError, "symlinks"):
            OfflineChatStore(path)
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "unrelated sensitive content")

    def test_existing_world_readable_sqlite_is_rejected(self):
        import os
        if os.name == "nt":
            self.skipTest("Windows local database ACLs use a different policy")
        path = self.root / "permissive.sqlite"
        path.write_bytes(b"")
        path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeContractError, "chmod 600"):
            OfflineChatStore(path)
        path.chmod(0o600)
        with OfflineChatStore(path) as restored:
            self.assertEqual(restored.list_sessions(
                self.product.model_digest, self.product.tokenizer_digest
            ), ())

    def test_existing_symlink_or_hardlink_sqlite_is_rejected(self):
        import os
        if os.name == "nt":
            self.skipTest("POSIX hard-link protection")
        path = self.root / "private.sqlite"
        with OfflineChatStore(path):
            pass
        alias = self.root / "alias.sqlite"
        alias.symlink_to(path)
        with self.assertRaisesRegex(RuntimeContractError, "symlinks"):
            OfflineChatStore(alias)
        hardlink = self.root / "hardlink.sqlite"
        os.link(path, hardlink)
        with self.assertRaisesRegex(RuntimeContractError, "hard-linked"):
            OfflineChatStore(hardlink)

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
