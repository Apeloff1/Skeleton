"""Desktop offline AI durability tests using the existing native inference plane.

No Tk display, provider credentials, network, Docker, or external weights.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import (
    DurableOfflineAISession, OfflineAIError, private_desktop_database,
)
from skeleton.cortex.transformer import TinyTransformer


def _backend(seed: int = 41) -> NativeRuntimeLocalModel:
    # This fixture proves execution and recovery only: untrained weights.
    runtime = NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=96, seed=seed, n_heads=2, n_layers=2, d_ff=16,
    ))
    return NativeRuntimeLocalModel(runtime)


class OfflineDesktopPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "desktop.sqlite3"
        self.backend = _backend()

    def _session(self, session_id: str | None = None) -> DurableOfflineAISession:
        return DurableOfflineAISession(
            self.backend, database=self.database, session_id=session_id
        )

    def test_generated_native_turn_is_durable_and_recovers(self):
        chat = self._session()
        session_id = chat.session_id
        result = asyncio.run(chat.ask("hello", max_output_tokens=2))
        self.assertEqual(result.model_digest, self.backend.model_digest)
        self.assertEqual(len(result.execution_receipt_digest), 64)
        self.assertEqual(chat.history[0], ("user", "hello"))
        self.assertEqual(chat.history[1][0], "assistant")
        self.assertEqual(chat.list_conversations()[0], (session_id, 1))
        chat.close()
        reopened = self._session(session_id)
        self.assertEqual(reopened.history, chat.history)
        follow_up = asyncio.run(reopened.ask("world", max_output_tokens=2))
        self.assertEqual(follow_up.model_digest, self.backend.model_digest)
        self.assertEqual(len(reopened.history), 4)
        self.assertEqual(reopened.list_conversations()[0], (session_id, 2))
        reopened.close()

    def test_new_switch_resume_and_delete_restore_previous_context(self):
        chat = self._session()
        first = chat.session_id
        asyncio.run(chat.ask("hello", max_output_tokens=2))
        original_history = chat.history
        second = chat.create_conversation()
        self.assertNotEqual(first, second)
        self.assertEqual(chat.history, ())
        asyncio.run(chat.ask("world", max_output_tokens=2))
        chat.resume(first)
        self.assertEqual(chat.history, original_history)
        chat.delete_conversation(first)
        self.assertNotEqual(chat.session_id, first)
        self.assertEqual(chat.history, ())
        self.assertNotIn(first, tuple(sid for sid, _ in chat.list_conversations()))
        chat.close()

    def test_concurrent_writer_requires_reload_not_silent_overwrite(self):
        first = self._session()
        second = self._session(first.session_id)
        asyncio.run(first.ask("hello", max_output_tokens=2))
        with self.assertRaisesRegex(OfflineAIError, "changed on disk"):
            asyncio.run(second.ask("world", max_output_tokens=2))
        self.assertEqual(second.history, ())
        second.resume(first.session_id)
        self.assertEqual(second.history, first.history)
        first.close()
        second.close()

    def test_inference_failure_leaves_previous_durable_revision_untouched(self):
        chat = self._session()
        sid = chat.session_id

        async def broken(*args, **kwargs):
            raise RuntimeError("deliberate inference fault")

        with patch.object(chat.engine, "generate", side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, "inference fault"):
                asyncio.run(chat.ask("hello", max_output_tokens=2))
        self.assertEqual(chat.history, ())
        self.assertEqual(chat.store.load(
            sid, self.backend.model_digest, self.backend.tokenizer_digest
        ).revision, 0)
        chat.close()

    def test_storage_failure_rolls_back_ephemeral_inference(self):
        chat = self._session()
        sid = chat.session_id
        with patch.object(chat.store, "commit",
                          side_effect=RuntimeContractError("disk full")):
            with self.assertRaisesRegex(RuntimeContractError, "disk full"):
                asyncio.run(chat.ask("hello", max_output_tokens=2))
        self.assertEqual(chat.history, ())
        self.assertEqual(chat.store.load(
            sid, self.backend.model_digest, self.backend.tokenizer_digest
        ).revision, 0)
        chat.close()

    def test_exact_model_digest_fences_restored_session(self):
        first = self._session()
        old_id = first.session_id
        first.close()
        drifted = _backend(seed=93)
        with self.assertRaisesRegex(RuntimeContractError, "different model"):
            DurableOfflineAISession(
                drifted, database=self.database, session_id=old_id
            )

    def test_offline_desktop_export_and_reimport_full_history(self):
        chat = self._session()
        asyncio.run(chat.ask("hello", max_output_tokens=2))
        old_id = chat.session_id
        old_history = chat.history
        bundle = chat.export_conversation(old_id)
        new_id = chat.import_conversation(bundle)
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(chat.session_id, new_id)
        self.assertEqual(chat.history, old_history)
        self.assertEqual(chat.store.load(
            new_id, self.backend.model_digest, self.backend.tokenizer_digest
        ).revision, 1)
        chat.close()

    def test_import_system_instruction_is_preserved_for_next_native_request(self):
        from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
        with OfflineChatStore(self.database) as store:
            sid = store.create(
                self.backend.model_digest, self.backend.tokenizer_digest,
                system="Follow the local operator's instructions.",
            )
            bundle = store.export_bundle(
                sid, self.backend.model_digest, self.backend.tokenizer_digest
            )
        chat = self._session()
        restored = chat.import_conversation(bundle)
        self.assertEqual(restored, chat.session_id)
        self.assertEqual(
            chat.instructions, "Follow the local operator's instructions."
        )
        self.assertEqual(chat.history, ())
        answer = asyncio.run(chat.ask("hello", max_output_tokens=2))
        self.assertEqual(answer.model_digest, self.backend.model_digest)
        saved = chat.store.load(
            restored, self.backend.model_digest, self.backend.tokenizer_digest
        )
        self.assertEqual(saved.transcript.messages[0].role, "system")
        self.assertEqual(saved.transcript.messages[1].content, "hello")
        chat.close()

    def test_private_database_directory_is_model_bound(self):
        with patch("pathlib.Path.home", return_value=Path(self.temp.name)):
            p = private_desktop_database(self.backend.model_digest)
            self.assertTrue(p.parent.is_dir())
            self.assertEqual(p.name, self.backend.model_digest + ".sqlite3")
            with self.assertRaises(OfflineAIError):
                private_desktop_database("not-a-digest")


if __name__ == "__main__":
    unittest.main()
