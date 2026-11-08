"""Canonical tenant-scoped knowledge ingest rehabilitation, not release approval."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.context.knowledge_plane import (
    KnowledgeError, KnowledgePlane, KnowledgePolicy,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import (
    PrincipalBinding, establish_binding,
)


class QuarantinedKnowledgeRestoration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="knowledge-restoration-", dir=str(Path.home())
        )
        self.root = Path(self.temp.name)
        self.identity = Identity("tenant", "researcher", "a" * 64, "b" * 64)
        establish_binding(
            self.root,
            PrincipalBinding("tenant", "researcher", "a" * 64, "b" * 64),
        )
        self.db = SpineDatabase(self.root)
        self.knowledge = KnowledgePlane(
            self.db, self.identity,
            policy=KnowledgePolicy(max_document_bytes=32768,
                                   max_total_bytes=200000,
                                   max_documents=16,
                                   max_chunks=64,
                                   max_scan_rows=1000),
        )

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def admit(self, body: bytes, *, revision: int = 0, doc_id: str = "original"):
        return self.knowledge.admit_bytes_for_tests(
            body, doc_id=doc_id, title="Source custody",
            rights="operator-authored", content_type="text/plain",
            expected_revision=revision, approved=True,
        )

    def test_service_uses_real_source_schema_not_legacy_unguarded_upsert(self):
        record = self.admit(b"alpha original source")
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["document_id"], "original")
        self.assertFalse(record["replayed"])
        with self.db.snapshot() as conn:
            docs = conn.execute(
                "SELECT principal, doc_id, revision FROM ai_kb_documents"
            ).fetchall()
            chunks = conn.execute(
                "SELECT principal,doc_id,revision FROM ai_kb_chunks"
            ).fetchall()
        self.assertEqual(len(docs), 1)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(docs[0][0], self.identity.key())
        self.assertEqual(chunks[0][0], self.identity.key())

    def test_retry_is_idempotent_but_changed_source_requires_correct_cas(self):
        initial = self.admit(b"alpha original source")
        replay = self.admit(b"alpha original source")
        self.assertEqual(replay["revision"], initial["revision"])
        self.assertTrue(replay["replayed"])
        with self.assertRaises(KnowledgeError):
            self.admit(b"beta changed source", revision=0)
        next_revision = self.admit(b"beta changed source", revision=1)
        self.assertEqual(next_revision["revision"], 2)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_kb_documents WHERE principal=? AND doc_id=?",
                (self.identity.key(), "original")
            ).fetchone()[0], 2)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_kb_documents WHERE principal=? AND active=1",
                (self.identity.key(),)
            ).fetchone()[0], 1)

    def test_transaction_failure_rolls_back_document_chunks_and_fts(self):
        self.admit(b"alpha original source")
        with patch(
            "skeleton.ai.runtime.operational_ai.context.knowledge_plane.ingest.events.append",
            side_effect=RuntimeError("transaction-test-injection")
        ):
            with self.assertRaises(RuntimeError):
                self.admit(b"beta changed source", revision=1)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_kb_documents"
            ).fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_kb_chunks"
            ).fetchone()[0], 1)
            self.assertEqual(conn.execute(
                'SELECT COUNT(*) FROM ai_kb_fts WHERE ai_kb_fts MATCH ?',
                ('"beta"',)
            ).fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT active FROM ai_kb_documents"
            ).fetchone()[0], 1)

    def test_explicit_operator_approval_required_for_import_and_forget(self):
        with self.assertRaises(KnowledgeError):
            self.knowledge.admit_bytes_for_tests(
                b"no consent", doc_id="original", title="No approval",
                approved=False,
            )
        self.admit(b"operator approved source")
        with self.assertRaises(KnowledgeError):
            self.knowledge.forget("original", expected_revision=1,
                                  approved=False)
        self.assertTrue(
            self.knowledge.forget("original", expected_revision=1,
                                  approved=True)
        )
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT active, deleted FROM ai_kb_documents"
            ).fetchone(), (0, 1))

    def test_wrong_or_unbound_tenant_cannot_write_into_existing_scope(self):
        other = Identity("another-tenant", "researcher", "a" * 64, "b" * 64)
        with self.assertRaises(Exception):
            KnowledgePlane(self.db, other, initialize=False).admit_bytes_for_tests(
                b"out-of-tenant source", doc_id="original",
                title="Wrong tenant", approved=True,
            )
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM ai_kb_documents"
            ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
