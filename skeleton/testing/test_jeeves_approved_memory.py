"""Approved memory lifecycle regressions against the canonical SQLite authority."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from hashlib import sha256

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _digest_request
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.app.jeeves_approved_memory import (
    ApprovedMemory, MemoryConflict, MemoryRejected, _features,
)

MODEL = "a" * 64
TOKENIZER = "b" * 64


def pin(row):
    return {key: row[key] for key in ("memory_id", "revision", "sha256")}


def hash_text(text):
    return sha256(text.encode("utf-8")).hexdigest()


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.db = OfflineChatStore(":memory:")
        self.memory = ApprovedMemory(self.db, MODEL, TOKENIZER)

    def tearDown(self):
        self.db.close()

    def save(self, **overrides):
        data = dict(kind="preference", label="Writing format",
                    text="Use short paragraphs about the Lantern audio project.",
                    tags=["Lantern", "writing"], expires_at=None,
                    source=None, approved=True)
        data.update(overrides)
        return self.memory.save(**data)

    def commit(self, sid, question, answer):
        row = self.db.load(sid, MODEL, TOKENIZER)
        transcript = row.transcript.append("user", question).append("assistant", answer)
        self.db.commit(session=row, request_id="r_" + str(row.revision+1),
                       request_digest=_digest_request(question, GenerationConfig(max_new_tokens=32)),
                       transcript=transcript, text=answer,
                       output_digest=hash_text(answer), prompt_tokens=12,
                       generated_tokens=3)
        return self.db.load(sid, MODEL, TOKENIZER)

    def source(self, sid, text, start=0, end=None):
        stored = self.db.load(sid, MODEL, TOKENIZER)
        end = len(text) if end is None else end
        return {"session_id": sid, "revision": stored.revision, "message_index": 0,
                "message_sha256": hash_text(text), "span_start": start, "span_end": end,
                "excerpt_sha256": hash_text(text[start:end])}

    def test_create_and_revision_cas(self):
        first = self.save()
        self.assertEqual(first["revision"], 1)
        second = self.save(text="Use detailed prose.", pin=pin(first), tags=["style"])
        self.assertEqual(first["memory_id"], second["memory_id"])
        self.assertEqual(second["revision"], 2)
        self.assertNotEqual(first["sha256"], second["sha256"])
        with self.assertRaises(MemoryConflict):
            self.save(pin=pin(first))
        self.assertEqual(self.memory.search("Lantern")["records"], [])
        self.assertEqual(self.memory.search("detailed prose")["records"][0]["memory_id"],
                         second["memory_id"])

    def test_explicit_approval_only(self):
        for bad in (False, None, "true", 1):
            with self.subTest(bad=bad), self.assertRaises(MemoryRejected):
                self.save(approved=bad)
        self.assertEqual(self.memory.list()["records"], [])

    def test_scope_isolation_and_no_foreign_replace_or_delete(self):
        own = self.save()
        other = ApprovedMemory(self.db, "c"*64, TOKENIZER)
        self.assertEqual(other.list()["records"], [])
        self.assertEqual(other.search("Lantern")["records"], [])
        with self.assertRaises(MemoryConflict):
            other.compose("Recall the preferences.", [pin(own)])
        with self.assertRaises(MemoryConflict):
            other.delete(pin(own), approved=True)
        third = ApprovedMemory(self.db, MODEL, "d"*64)
        self.assertEqual(third.list()["records"], [])

    def test_indexed_recall_with_unicode_and_typo(self):
        row = self.save(label="Norwegian dialogue", text="Måneskinn and blåbær; Lantern audio.",
                        tags=["norsk", "音楽制作環境"])
        for term in ("MÅNESKINN", "blaabær blåbær", "Lantren", "音楽制作"):
            with self.subTest(term=term):
                results = self.memory.search(term)["records"]
                self.assertTrue(results)
                self.assertEqual(results[0]["memory_id"], row["memory_id"])
        self.assertEqual(self.memory.search("Lantern", kinds=["goal"])["records"], [])

    def test_index_feature_bound_and_normalization(self):
        self.assertLessEqual(len(_features(" ".join("note"+str(i) for i in range(1000)))), 192)
        self.assertIn("w:åse", _features("ÅSE"))
        self.assertIn("g:音楽", _features("音楽制作"))

    def test_expiry_non_destructive_and_stale_pin(self):
        with patch("skeleton.app.jeeves_approved_memory.time.time", return_value=1000):
            row = self.save(expires_at=1002)
            self.assertTrue(self.memory.list()["records"][0]["active"])
        with patch("skeleton.app.jeeves_approved_memory.time.time", return_value=1002):
            self.assertEqual(self.memory.list()["records"], [])
            self.assertEqual(self.memory.search("Lantern")["records"], [])
            self.assertFalse(self.memory.list(include_expired=True)["records"][0]["active"])
            with self.assertRaises(MemoryConflict):
                self.memory.compose("Continue", [pin(row)])
            renewed = self.save(pin=pin(row), expires_at=None)
            self.assertTrue(renewed["active"])

    def test_delete_requires_exact_pin_and_removes_index(self):
        row = self.save()
        with self.assertRaises(MemoryRejected):
            self.memory.delete(pin(row), approved=False)
        with self.assertRaises(MemoryConflict):
            self.memory.delete({**pin(row),"revision":2}, approved=True)
        result = self.memory.delete(pin(row), approved=True)
        self.assertFalse(result["previous_chat_copies_deleted"])
        self.assertEqual(self.memory.list()["records"], [])
        self.assertEqual(self.db._db.execute("SELECT count(*) FROM jeeves_memory_terms").fetchone()[0], 0)

    def test_compose_exact_selection_and_read_only(self):
        a = self.save()
        b = self.save(kind="goal", label="Roadmap", text="Finish the glossary.", tags=[])
        out = self.memory.compose("Continue our project.", [pin(a)])
        self.assertIn(a["text"], out["composed_text"])
        self.assertNotIn(b["text"], out["composed_text"])
        self.assertEqual(out["draft_sha256"], hash_text("Continue our project."))
        self.assertEqual(out["composed_sha256"], hash_text(out["composed_text"]))
        self.assertTrue(out["read_only"])
        self.assertFalse(out["generation_performed"])
        self.assertFalse(out["automatic_injection"])
        self.assertEqual(out, self.memory.compose("Continue our project.", [pin(a)]))
        self.assertEqual(len(self.memory.list()["records"]), 2)
        self.save(pin=pin(a), text="New approved format.")
        with self.assertRaises(MemoryConflict):
            self.memory.compose("Continue our project.", [pin(a)])

    def test_composition_budget_and_duplicates(self):
        row = self.save()
        for pins, limit in (([pin(row),pin(row)],4096), ([pin(row)],10),
                            ([],4096), ([pin(row)],4097)):
            with self.assertRaises(MemoryRejected):
                self.memory.compose("Continue", pins, max_bytes=limit)

    def test_source_exact_excerpt_and_cascade(self):
        sid = self.db.create(MODEL, TOKENIZER)
        question = "Project Lantren uses FLAC."
        self.commit(sid, question, "Acknowledged.")
        src = self.source(sid, question, 8)
        note = self.save(text=question[8:], source=src)
        self.assertEqual(note["source"], src)
        for bad in ({**src,"message_sha256":"f"*64}, {**src,"span_start":0},
                    {**src,"message_index":1}):
            with self.assertRaises(MemoryConflict):
                self.save(text=question[8:], source=bad)
        self.commit(sid, "What is next?", "Prepare a plan.")
        with self.assertRaises(MemoryConflict):
            self.save(text=question[8:], source=src)
        edited = self.save(text=question[8:], source=src, pin=pin(note), label="New label")
        self.assertEqual(edited["revision"], 2)
        self.db.delete(sid, MODEL, TOKENIZER)
        self.assertEqual(self.memory.list()["records"], [])
        self.assertEqual(self.db._db.execute("SELECT count(*) FROM jeeves_memory_terms").fetchone()[0], 0)

    def test_tampered_index_and_record_are_rejected(self):
        row = self.save()
        self.db._db.execute("DELETE FROM jeeves_memory_terms WHERE memory_id=? AND term=?",
                            (row["memory_id"], "w:lantern"))
        with self.assertRaises(MemoryRejected):
            self.memory.list()
        # Explicit deletion remains possible even if its derived index is broken.
        self.memory.delete(pin(row), approved=True)
        row = self.save()
        self.db._db.execute("UPDATE jeeves_approved_memory SET note=? WHERE memory_id=?",
                            ("foreign text", row["memory_id"]))
        with self.assertRaises(MemoryRejected):
            self.memory.compose("Question", [pin(row)])

    def test_validation_rejects_bad_text_and_tags(self):
        for fields in ({"text":"\x00"}, {"text":"é"*1000}, {"text":"\ud800"},
                       {"tags":["A","a"]}, {"tags":[1]}, {"label":" "},
                       {"expires_at":True}, {"kind":"untrusted"}):
            with self.subTest(fields=repr(fields)[:80]), self.assertRaises(MemoryRejected):
                self.save(**fields)

    def test_pagination_has_unique_records(self):
        for i in range(12):
            self.save(kind="goal", text="Objective " + str(i), tags=[])
        seen, cursor = [], None
        while True:
            page = self.memory.list(cursor=cursor, limit=3)
            seen.extend(r["memory_id"] for r in page["records"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 12)
        self.assertEqual(len(set(seen)), 12)

    def test_restart_preserves_memory_and_cas(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"private.sqlite3"
            with OfflineChatStore(path) as store:
                persisted = ApprovedMemory(store, MODEL, TOKENIZER)
                row = persisted.save(kind="goal", label="Glossary", text="Finish glossary.",
                                     tags=[], expires_at=None, source=None, approved=True)
            with OfflineChatStore(path) as store:
                persisted = ApprovedMemory(store, MODEL, TOKENIZER)
                self.assertEqual(persisted.list()["records"][0]["sha256"], row["sha256"])
                persisted.delete(pin(row), approved=True)
                self.assertEqual(persisted.list()["records"], [])


if __name__ == "__main__":
    unittest.main()
