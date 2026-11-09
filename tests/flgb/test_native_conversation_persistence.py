"""Executable integration coverage for native chat persistence and serving."""
import os
import tempfile
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import (
    ConversationStore,
    DurableConversationCoordinator,
    GenerationConfig,
    NativeConversationService,
    NativeConversationSession,
    NativeLLMRuntime,
    RuntimeContractError,
)


def runtime():
    model = TinyTransformer(
        vocab=("hello", "world", "again", "small", "runtime", "token"),
        dim=8, ctx=16, seed=11, n_heads=2, n_layers=2, d_ff=16,
    )
    return NativeLLMRuntime(model)


class NativeConversationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = runtime()
        self.store = ConversationStore(os.path.join(self.tmp.name, "chat.db"), self.runtime)
        self.service = NativeConversationService(self.runtime, max_sessions=8)
        self.coordinator = DurableConversationCoordinator(self.service, self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_restart_round_trip(self):
        sid = self.coordinator.create()
        self.service.append_text(sid, "hello world")
        before = self.service.tokens(sid)
        self.coordinator.save(sid)
        self.coordinator.detach(sid)
        self.coordinator.attach(sid)
        self.assertEqual(self.service.tokens(sid), before)

    def test_stale_database_writer_fails_closed(self):
        sid = self.coordinator.create()
        binding = self.coordinator.binding(sid)
        self.store.pin(sid, binding.durable_revision, True)
        self.service.append_text(sid, "hello")
        with self.assertRaises(RuntimeContractError):
            self.coordinator.save(sid)

    def test_bulk_checkpoint_is_atomic(self):
        first, second = self.coordinator.create(), self.coordinator.create()
        self.service.append_text(first, "hello")
        self.service.append_text(second, "world")
        self.store.pin(second, 0, True)
        with self.assertRaises(RuntimeContractError):
            self.coordinator.save_all()
        self.assertEqual(self.store.load(first).revision, 0)

    def test_dirty_checkpoint(self):
        sid = self.coordinator.create()
        self.assertEqual(self.coordinator.dirty_ids(), ())
        self.service.append_text(sid, "hello")
        self.assertEqual(self.coordinator.dirty_ids(), (sid,))
        self.coordinator.save_dirty()
        self.assertEqual(self.coordinator.dirty_ids(), ())

    def test_restore_rejects_other_model(self):
        sid = self.coordinator.create()
        self.coordinator.save(sid)
        # Use a deterministic different seed to test incompatible model weights.
        different = NativeLLMRuntime(TinyTransformer(
            vocab=("hello", "world", "again", "small", "runtime", "token"),
            dim=8, ctx=16, seed=99, n_heads=2, n_layers=2, d_ff=16))
        with self.assertRaises(RuntimeContractError):
            NativeConversationSession.restore(different, self.store.load(sid).snapshot)

    def test_generation_persists_token_native_history(self):
        sid = self.coordinator.create()
        result = self.service.generate(sid, "hello world",
                                       GenerationConfig(max_new_tokens=2, temperature=0.0))
        self.assertEqual(self.service.turns(sid), 1)
        self.assertTrue(result.generated_ids)
        expected = self.service.tokens(sid)
        self.coordinator.save(sid)
        self.coordinator.detach(sid)
        self.coordinator.attach(sid)
        self.assertEqual(self.service.tokens(sid), expected)

    def test_backup_restores_committed_state(self):
        sid = self.coordinator.create(pinned=True)
        self.service.append_text(sid, "hello")
        self.coordinator.save(sid)
        backup_path = os.path.join(self.tmp.name, "backup.db")
        self.store.backup_to(backup_path)
        backup = ConversationStore(backup_path, self.runtime)
        try:
            self.assertEqual(backup.restore_session(sid).token_ids,
                             self.service.tokens(sid))
            self.assertTrue(backup.load(sid).pinned)
        finally:
            backup.close()

    def test_atomic_cohort_checkpoint_preserves_pins(self):
        first, second = self.coordinator.create(), self.coordinator.create()
        self.service.pin(second)
        self.service.append_text(first, "hello")
        self.coordinator.save_all()
        self.assertTrue(self.store.load(second).pinned)
        self.assertEqual(self.store.restore_session(first).token_ids,
                         self.service.tokens(first))

    def test_restart_recovery(self):
        first, second = self.coordinator.create(), self.coordinator.create()
        self.service.append_text(first, "hello")
        self.coordinator.save(first)
        self.coordinator.detach(first)
        self.coordinator.detach(second)
        restored = self.coordinator.recover_all()
        self.assertEqual(set(restored), {first, second})
        self.assertEqual(self.service.text(first), "hello")

    def test_foreign_runtime_storage_rejected(self):
        other = runtime()
        session = NativeConversationSession(other)
        with self.assertRaises(RuntimeContractError):
            self.store.create("foreign-session", session)

    def test_checkpoint_detach(self):
        sid = self.coordinator.create()
        self.service.append_text(sid, "hello")
        self.coordinator.checkpoint_and_detach(sid)
        self.assertFalse(self.service.exists(sid))
        self.assertTrue(self.store.exists(sid))

    def test_revision_conflict_rejects_stale_mutation(self):
        sid = self.coordinator.create()
        revision = self.service.revision(sid)
        self.service.append_text(sid, "hello")
        with self.assertRaises(RuntimeContractError):
            self.service.compare_and_reset(sid, revision)


if __name__ == "__main__":
    unittest.main()
