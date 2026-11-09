"""Integration coverage for the native chat workspace UX state machine."""
import unittest

from skeleton.ai.model_runtime import (
    ChatMessage, ChatTranscript, NativeChatWorkspace, RuntimeContractError,
)


class NativeChatWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.workspace = NativeChatWorkspace(max_conversations=20)
        self.cid = self.workspace.create(title="Research")

    def test_edit_undo_redo(self):
        w = self.workspace
        w.append(self.cid, "user", "original")
        w.edit_message(self.cid, 0, "edited")
        self.assertEqual(w.get(self.cid).messages[0].content, "edited")
        w.undo(self.cid)
        self.assertEqual(w.get(self.cid).messages[0].content, "original")
        w.redo(self.cid)
        self.assertEqual(w.get(self.cid).messages[0].content, "edited")

    def test_revision_conflict(self):
        w = self.workspace
        revision = w.revision(self.cid)
        w.append(self.cid, "user", "hello")
        with self.assertRaises(RuntimeContractError):
            w.append(self.cid, "user", "stale", expected_revision=revision)

    def test_fork_is_independent(self):
        w = self.workspace
        w.append(self.cid, "user", "original")
        fork = w.fork(self.cid)
        w.append(fork, "assistant", "branch")
        self.assertEqual(len(w.get(self.cid).messages), 1)
        self.assertEqual(len(w.get(fork).messages), 2)

    def test_search_and_tags(self):
        w = self.workspace
        w.append(self.cid, "user", "Searchable Alpha")
        w.add_tag(self.cid, "research")
        self.assertEqual(len(w.search("alpha")), 1)
        self.assertIn(self.cid, w.filter_tag("research"))
        self.assertIn(self.cid, w.search_titles("research"))

    def test_export_import_round_trip(self):
        w = self.workspace
        w.append(self.cid, "user", "hello")
        w.pin(self.cid)
        w.archive(self.cid)
        restored = w.import_json(w.export_json(self.cid))
        self.assertEqual(w.get(restored), w.get(self.cid))
        self.assertTrue(w.describe(restored).pinned)
        self.assertTrue(w.describe(restored).archived)

    def test_batch_delete_prevalidates(self):
        w = self.workspace
        with self.assertRaises(RuntimeContractError):
            w.delete_many((self.cid, "unknown"))
        self.assertTrue(w.exists(self.cid))

    def test_archived_pruning_preserves_pins(self):
        w = self.workspace
        w.archive(self.cid)
        w.pin(self.cid)
        self.assertEqual(w.prune_archived(older_than=9999999999), 0)
        w.unpin(self.cid)
        self.assertEqual(w.prune_archived(older_than=9999999999), 1)

    def test_event_stream_and_statistics(self):
        w = self.workspace
        w.append(self.cid, "user", "hello")
        self.assertEqual(w.stats()["messages"], 1)
        self.assertGreaterEqual(len(w.events(conversation_id=self.cid)), 2)

    def test_message_editing_and_navigation(self):
        w = self.workspace
        w.append_user(self.cid, "first")
        w.append_assistant(self.cid, "reply")
        self.assertEqual(w.last_user(self.cid).content, "first")
        self.assertEqual(w.last_assistant(self.cid).content, "reply")
        self.assertEqual(len(w.conversation_turns(self.cid)), 1)
        w.replace_last(self.cid, "assistant", "revised")
        self.assertEqual(w.last_assistant(self.cid).content, "revised")

    def test_insert_move_and_swap(self):
        w = self.workspace
        w.append_user(self.cid, "one")
        w.append_user(self.cid, "two")
        w.insert_message(self.cid, 1, ChatMessage("assistant", "middle"))
        self.assertEqual(w.message_count(self.cid), 3)
        w.move_message(self.cid, 1, 2)
        self.assertEqual(w.message_at(self.cid, 2).content, "middle")
        w.swap_messages(self.cid, 0, 1)
        self.assertEqual(w.message_at(self.cid, 0).content, "two")

    def test_metadata_compare_and_swap(self):
        w = self.workspace
        revision = w.revision(self.cid)
        updated = w.compare_and_rename(self.cid, revision, "Updated")
        self.assertEqual(w.describe(self.cid).title, "Updated")
        with self.assertRaises(RuntimeContractError):
            w.compare_and_archive(self.cid, revision)
        self.assertGreater(updated, revision)

    def test_copy_between_branches(self):
        w = self.workspace
        w.append_user(self.cid, "hello")
        branch = w.fork(self.cid)
        w.copy_message(self.cid, 0, branch)
        self.assertEqual(w.message_count(branch), 2)
        self.assertEqual(w.message_count(self.cid), 1)

    def test_undo_redo_history_is_bounded(self):
        w = NativeChatWorkspace(max_history=2)
        cid = w.create()
        for i in range(8):
            w.append_user(cid, str(i))
        self.assertEqual(w.history_depth(cid)[0], 2)
        w.undo(cid)
        w.undo(cid)
        self.assertEqual(w.history_depth(cid)[1], 2)
        with self.assertRaises(RuntimeContractError):
            w.undo(cid)

    def test_batch_delete_rejects_invalid_identifiers_atomically(self):
        w = self.workspace
        with self.assertRaises(RuntimeContractError):
            w.delete_many((self.cid, None))
        self.assertTrue(w.exists(self.cid))

    def test_search_rejects_scalar_role_filter(self):
        w = self.workspace
        w.append_user(self.cid, "hello")
        with self.assertRaises(RuntimeContractError):
            w.search("hello", roles="user")

    def test_tags_reject_unhashable_items(self):
        w = self.workspace
        with self.assertRaises(RuntimeContractError):
            w.set_tags(self.cid, (["invalid"],))
        self.assertEqual(w.describe(self.cid).tags, ())

    def test_capacity_limit(self):
        w = NativeChatWorkspace(max_conversations=1)
        w.create()
        with self.assertRaises(RuntimeContractError):
            w.create()


if __name__ == "__main__":
    unittest.main()
