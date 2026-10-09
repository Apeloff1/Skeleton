"""Tamper/replay/backup/fork verification for atomic offline source-bound turns.

Evidence custody proves *supplied context*, not model factual correctness.
All tests use real SQLite transactions and immutable source-byte digests.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime.offline_chat import (
    OfflineChatStore, _digest_request, _stable_bytes,
)
from skeleton.ai.model_runtime.runtime_contracts import (
    GenerationConfig, RuntimeContractError,
)
from skeleton.app.offline_grounding import (
    grounded_request_digest, prepare_evidence, validate_evidence,
)
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary


class GroundedOfflineReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "grounding.sqlite3"
        self.store = OfflineChatStore(self.path)
        self.addCleanup(self.store.close)
        self.model = "a" * 64
        self.token = "b" * 64
        self.refs = OfflineKnowledgeLibrary(self.store, self.model, self.token)
        self.question = "How does the depth buffer reject pixels?"
        self.source = (
            "The depth buffer stores a depth value for each pixel. "
            "Fragments outside the visible depth range are rejected."
        )
        self.document = self.refs.add_text("GPU pipeline", self.source)
        self.sid = self.store.create(self.model, self.token)
        self.config = GenerationConfig(max_new_tokens=2)
        self.digest = grounded_request_digest(
            _digest_request(self.question, self.config)
        )

    def _snapshot(self):
        hits = self.refs.search("depth buffer pixels", limit=2)
        self.assertTrue(hits)
        return prepare_evidence(
            self.question, self.digest, hits, self.model, self.token
        )

    def _commit(self, evidence=None, *, req="grounded-one"):
        saved = self.store.load(self.sid, self.model, self.token)
        transcript = saved.transcript.append("user", self.question).append(
            "assistant", "A local model output."
        )
        receipt = self.store.commit(
            session=saved, request_id=req, request_digest=self.digest,
            transcript=transcript, text="A local model output.",
            output_digest=sha256(b"A local model output.").hexdigest(),
            prompt_tokens=21, generated_tokens=2,
            evidence_manifest=evidence,
        )
        return receipt

    def test_atomic_commit_roundtrip_and_delete_source_snapshot_survives(self):
        manifest = self._snapshot()
        original = self._commit(manifest)
        self.assertEqual(original.revision, 1)
        self.assertEqual(self.store.turn_evidence(
            self.sid, self.model, self.token
        ), [manifest])
        self.refs.delete(self.document["document_id"])
        self.assertEqual(self.refs.search("depth"), [])
        self.assertEqual(self.store.turn_evidence(
            self.sid, self.model, self.token
        ), [manifest])
        self.store.close()
        self.store = OfflineChatStore(self.path)
        self.refs = OfflineKnowledgeLibrary(self.store, self.model, self.token)
        self.assertEqual(self.store.load(
            self.sid, self.model, self.token
        ).revision, 1)
        self.assertEqual(self.store.turn_evidence(
            self.sid, self.model, self.token
        ), [manifest])
        self.assertEqual(self.store.replay(
            self.sid, "grounded-one", self.digest
        ).text, original.text)

    def test_grounded_backup_v2_and_old_plain_v1_both_roundtrip(self):
        manifest = self._snapshot()
        self._commit(manifest)
        archive = self.store.export_bundle(self.sid, self.model, self.token)
        envelope = json.loads(archive)
        self.assertEqual(
            envelope["body"]["schema"], "skeleton.ai.offline-chat-bundle.v2"
        )
        self.assertEqual(envelope["body"]["evidence"], [manifest])
        restored = self.store.import_bundle(
            archive, self.model, self.token
        )
        self.assertNotEqual(self.sid, restored)
        self.assertEqual(self.store.turn_evidence(
            restored, self.model, self.token
        ), [manifest])
        self.assertEqual(self.store.load(
            restored, self.model, self.token
        ).revision, 1)

        other = self.store.create(self.model, self.token)
        original = self.sid
        self.sid = other
        try:
            self._commit(None, req="legacy")
        finally:
            self.sid = original
        plain = self.store.export_bundle(other, self.model, self.token)
        self.assertEqual(
            json.loads(plain)["body"]["schema"],
            "skeleton.ai.offline-chat-bundle.v1"
        )
        imported = self.store.import_bundle(plain, self.model, self.token)
        self.assertEqual(self.store.turn_evidence(
            imported, self.model, self.token
        ), [None])

    def test_fork_exact_prefix_copies_grounding_and_delete_cascades(self):
        manifest = self._snapshot()
        self._commit(manifest)
        branch = self.store.fork(self.sid, self.model, self.token)
        self.assertEqual(self.store.turn_evidence(
            branch, self.model, self.token
        ), [manifest])
        empty = self.store.fork(
            self.sid, self.model, self.token, after_turn=0
        )
        self.assertEqual(self.store.turn_evidence(
            empty, self.model, self.token
        ), [])
        self.store.delete(self.sid, self.model, self.token)
        self.assertEqual(self.store.turn_evidence(
            branch, self.model, self.token
        ), [manifest])
        self.assertEqual(self.store._db.execute(
            "SELECT COUNT(*) FROM offline_turn_evidence "
            "WHERE session_id=?", (self.sid,)
        ).fetchone()[0], 0)

    def test_poisoned_evidence_cannot_be_loaded_or_backed_up(self):
        self._commit(self._snapshot())
        with self.store._transaction():
            self.store._db.execute(
                "UPDATE offline_turn_evidence SET evidence_json=? "
                "WHERE session_id=?", ('{"forged":true}', self.sid),
            )
        for task in (
            lambda: self.store.load(self.sid, self.model, self.token),
            lambda: self.store.export_bundle(self.sid, self.model, self.token),
        ):
            with self.assertRaises(RuntimeContractError):
                task()

    def test_manipulated_backup_rehash_does_not_launder_fake_citation(self):
        self._commit(self._snapshot())
        envelope = json.loads(
            self.store.export_bundle(self.sid, self.model, self.token)
        )
        envelope["body"]["evidence"][0]["citations"][0]["passage"] = "fake passage"
        envelope["sha256"] = sha256(
            _stable_bytes(envelope["body"])
        ).hexdigest()
        with self.assertRaises(RuntimeContractError):
            self.store.import_bundle(
                _stable_bytes(envelope), self.model, self.token
            )

    def test_cancelled_generation_has_no_orphan_evidence(self):
        manifest = self._snapshot()
        saved = self.store.load(self.sid, self.model, self.token)
        attempted = saved.transcript.append("user", self.question).append(
            "assistant", "forged result"
        )
        invalid = dict(manifest)
        invalid["context_sha256"] = "0" * 64
        with self.assertRaises(RuntimeContractError):
            self.store.commit(
                session=saved, request_id="bad", request_digest=self.digest,
                transcript=attempted, text="forged result",
                output_digest=sha256(b"forged result").hexdigest(),
                prompt_tokens=20, generated_tokens=1,
                evidence_manifest=invalid,
            )
        self.assertEqual(self.store.load(
            self.sid, self.model, self.token
        ).revision, 0)
        self.assertEqual(self.store._db.execute(
            "SELECT COUNT(*) FROM offline_turn_evidence"
        ).fetchone()[0], 0)

    def test_mode_separation_prevents_same_id_plain_reuse(self):
        self._commit(self._snapshot())
        with self.assertRaisesRegex(RuntimeContractError, "request id reused"):
            self.store.replay(
                self.sid, "grounded-one",
                _digest_request(self.question, self.config),
            )

    def test_strict_grounding_rejects_wrong_question_source_and_digest(self):
        manifest = self._snapshot()
        cases = [
            {**manifest, "question_sha256": "0" * 64},
            {**manifest, "model_digest": "0" * 64},
            {**manifest, "context": "rewritten source text"},
            {**manifest, "citations": []},
        ]
        for tampered in cases:
            with self.subTest(tampered=tuple(tampered.items())[:1]):
                with self.assertRaises(RuntimeContractError):
                    validate_evidence(
                        tampered, self.question, self.digest,
                        self.model, self.token,
                    )


if __name__ == "__main__":
    unittest.main()
