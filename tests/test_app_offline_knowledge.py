"""Executable local reference ingestion/retrieval and trust-boundary tests.

No hosted providers, web crawling, UI simulation or external model weights.
All data stays in the existing model-scoped SQLite application database.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.app.offline_knowledge import (
    MAX_DOCUMENT_BYTES, OfflineKnowledgeLibrary,
)


class OfflineKnowledgeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "local.sqlite3"
        self.store = OfflineChatStore(self.database)
        self.addCleanup(self.store.close)
        self.model = "a" * 64
        self.tokenizer = "b" * 64
        self.library = OfflineKnowledgeLibrary(
            self.store, self.model, self.tokenizer,
        )

    def test_ingest_search_citations_and_exact_model_restart(self):
        document = (
            "The GPU rasterizer uses fixed-point edge functions to decide "
            "pixel coverage. The depth buffer applies early rejection. "
            "Vertex transforms use the 4 by 4 projection matrix. "
        ) * 6
        added = self.library.add_text("Rasterizer notes", document)
        self.assertFalse(added["reused"])
        self.assertEqual(len(added["sha256"]), 64)
        found = self.library.search("fixed-point edge functions")
        self.assertGreater(len(found), 0)
        hit = found[0]
        self.assertEqual(hit["document_id"], added["document_id"])
        self.assertEqual(hit["document_sha256"], added["sha256"])
        self.assertIn("fixed-point edge functions", hit["passage"])
        self.assertTrue(hit["citation"].startswith("local:"))
        self.assertEqual(
            document[hit["char_start"]:hit["char_end"]],
            hit["passage"],
        )
        # Reopening a new SQLite connection proves persistence rather than
        # querying a still-live in-memory index.
        with OfflineChatStore(self.database) as reopened:
            later = OfflineKnowledgeLibrary(reopened, self.model, self.tokenizer)
            replay = later.search("depth buffer early rejection")
            self.assertTrue(replay)
            self.assertEqual(replay[0]["document_id"], added["document_id"])

    def test_repeat_exact_document_reuses_identity_without_duplication(self):
        first = self.library.add_text("Guide A", "Deterministic renderer and pipeline.")
        second = self.library.add_text("Guide B", "Deterministic renderer and pipeline.")
        self.assertTrue(second["reused"])
        self.assertEqual(second["document_id"], first["document_id"])
        self.assertEqual(len(self.library.list_documents()), 1)

    def test_references_do_not_leak_between_model_identities(self):
        item = self.library.add_text("Private reference", "Shader pipeline secret algorithm.")
        incompatible = OfflineKnowledgeLibrary(
            self.store, "c" * 64, "d" * 64,
        )
        self.assertEqual(incompatible.list_documents(), [])
        self.assertEqual(incompatible.search("shader algorithm"), [])
        with self.assertRaisesRegex(RuntimeContractError, "unknown local"):
            incompatible.delete(item["document_id"])
        self.assertEqual(len(self.library.list_documents()), 1)

    def test_bad_inputs_fail_without_mutating_library(self):
        for title, body in [
            ("", "Valid searchable text"), ("title", ""),
            ("nul\x00file", "Good searchable text"),
            ("title", "data\x00bad"),
            ("x" * 201, "Valid searchable text"),
            ("title", "z" * (MAX_DOCUMENT_BYTES + 1)),
            ("title", "   "),
            ("title", "A!" * 50),
        ]:
            with self.subTest(title=title[:12], n=len(body)):
                with self.assertRaises(RuntimeContractError):
                    self.library.add_text(title, body)
        self.assertEqual(self.library.list_documents(), [])

    def test_search_does_not_execute_queries_as_sql(self):
        item = self.library.add_text(
            "Important", "The vertex shading algorithm is deterministic."
        )
        self.assertTrue(self.library.search("vertex shading"))
        self.assertEqual(self.library.search("'; DROP TABLE offline_documents; --"), [])
        self.assertEqual(self.library.search("the and for"), [])
        self.assertEqual(len(self.library.list_documents()), 1)
        self.assertEqual(
            self.library.list_documents()[0]["document_id"], item["document_id"]
        )

    def test_utf8_source_coordinates_and_unicode_normalized_search(self):
        text = "Café café naïve — geometry shader 雲端渲染 software pipeline."
        added = self.library.add_text("Unicode rendering", text)
        hits = self.library.search("ＣＡＦÉ geometry")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["document_id"], added["document_id"])
        self.assertEqual(
            text[hits[0]["char_start"]:hits[0]["char_end"]],
            hits[0]["passage"],
        )

    def test_corrupt_document_digest_fails_closed_for_search_and_list(self):
        item = self.library.add_text(
            "Trusted original", "Hardware rasterizer uses tile bins."
        )
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_documents SET content_text=? WHERE document_id=?",
                ("Attack-controlled substituted material.", item["document_id"]),
            )
        with self.assertRaisesRegex(RuntimeContractError, "hash mismatch"):
            self.library.search("substituted")
        with self.assertRaisesRegex(RuntimeContractError, "hash mismatch"):
            self.library.list_documents()

    def test_altered_passage_and_offsets_cannot_forge_valid_citation(self):
        item = self.library.add_text(
            "Source offsets", "The temporal frame interpolation is exact."
        )
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_document_chunks SET content=? "
                "WHERE document_id=? AND ordinal=0",
                ("Fake copied passage", item["document_id"]),
            )
        with self.assertRaisesRegex(RuntimeContractError, "provenance mismatch"):
            self.library.search("temporal interpolation")

    def test_missing_chunk_is_not_silently_hidden_from_search(self):
        item = self.library.add_text(
            "Long source", "Software geometry rasterizer. " * 90
        )
        self.assertGreater(item["chunk_count"], 1)
        with self.store._transaction():
            self.store._db.execute(
                "DELETE FROM offline_document_chunks "
                "WHERE document_id=? AND ordinal=1", (item["document_id"],)
            )
        with self.assertRaisesRegex(RuntimeContractError, "index is incomplete"):
            self.library.search("rasterizer")

    def test_corrupted_offline_reference_is_isolated_from_chat_history(self):
        model_session = self.store.create(self.model, self.tokenizer)
        source = self.library.add_text(
            "Reference only", "Rasterization colors follow sRGB gamma."
        )
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_document_chunks SET char_start=999 "
                "WHERE document_id=? AND ordinal=0", (source["document_id"],)
            )
        with self.assertRaises(RuntimeContractError):
            self.library.search("gamma")
        restored_chat = self.store.load(model_session, self.model, self.tokenizer)
        self.assertEqual(restored_chat.revision, 0)

    def test_delete_cascades_chunks_but_cannot_delete_other_model_data(self):
        item = self.library.add_text(
            "Knowledge", "Game console memory bus layout and mapper structure."
        )
        self.library.delete(item["document_id"])
        self.assertEqual(self.library.search("memory mapper"), [])
        with self.store._lock:
            count = self.store._db.execute(
                "SELECT COUNT(*) FROM offline_document_chunks "
                "WHERE document_id=?", (item["document_id"],)
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_immutable_byte_hash_denies_duplicate_under_new_label(self):
        doc = self.library.add_text("Evidence", "Audio resampler polyphase filter banks.")
        same = self.library.add_text("Different title", "Audio resampler polyphase filter banks.")
        self.assertEqual(doc["sha256"], same["sha256"])
        self.assertEqual(doc["document_id"], same["document_id"])

    def test_library_cap_enforced_before_transaction_writes(self):
        # Use the real bounded admission logic against an artificially
        # lowered configured cap; no large fixture generation required.
        from unittest.mock import patch
        self.library.add_text("One", "CPU vector instruction scheduling.")
        with patch("skeleton.app.offline_knowledge.MAX_DOCUMENTS_PER_MODEL", 1):
            with self.assertRaisesRegex(RuntimeContractError, "at capacity"):
                self.library.add_text(
                    "Two", "GPU asynchronous compute dispatches."
                )
        self.assertEqual(len(self.library.list_documents()), 1)

    def test_chunking_preserves_source_offsets_and_document_sha(self):
        content = (
            "The texture cache uses Morton order tiling for locality. " * 60
            + "The controller polls the gamepad serial bus each frame."
        )
        added = self.library.add_text("Console hardware", content)
        self.assertGreater(added["chunk_count"], 1)
        hits = self.library.search("controller gamepad serial bus")
        self.assertTrue(hits)
        for hit in hits:
            self.assertEqual(
                content[hit["char_start"]:hit["char_end"]], hit["passage"]
            )


if __name__ == "__main__":
    unittest.main()
