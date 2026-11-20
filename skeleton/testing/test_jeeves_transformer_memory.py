"""Index contract fixtures and an optional actual synthetic ONNX inference test."""
from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.jeeves_approved_memory import ApprovedMemory, MemoryConflict, MemoryRejected
from skeleton.app.jeeves_sentence_encoder import EncoderSpec, EncoderUnavailable, SentenceEncoder, _read_pinned
from skeleton.app.jeeves_transformer_memory import TransformerMemoryIndex

MODEL = "a"*64
TOKENIZER = "b"*64
OTHER = "c"*64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(row):
    return {key: row[key] for key in ("memory_id","revision","sha256")}


def spec_for(root, **changes):
    data = {
        "model_path": str(Path(root)/"encoder.onnx"), "model_sha256": "d"*64,
        "tokenizer_path": str(Path(root)/"tokenizer.json"), "tokenizer_sha256": "e"*64,
        "output_name": "last_hidden_state", "dimensions": 4, "max_length": 16,
        "pooling": "mean", "threads": 1, "query_prefix": "", "document_prefix": "",
    }
    return EncoderSpec.parse(data | changes)


class FixtureEncoder:
    """Deterministic synthetic vectors; not a model or semantic quality evidence."""
    def __init__(self, spec, fail=False, callback=None):
        self.spec, self.fail, self.callback = spec, fail, callback
        self.closed = False
        self.calls = []

    def assert_stable(self):
        if self.closed:
            raise EncoderUnavailable("fixture encoder closed")

    def close(self):
        self.closed = True

    def qualification(self):
        if self.fail:
            raise EncoderUnavailable("fixture qualification failed")
        return {"encoder_identity": self.spec.identity, "document_vectors": 2,
                "query_vectors": 1, "dimensions": self.spec.dimensions,
                "query_path_executed": True, "document_path_executed": True,
                "input_truncation_enabled": True, "independent_quality_certified": False}

    def encode(self, texts, *, query):
        self.assert_stable()
        self.calls.append((list(texts), query))
        rows = []
        for text in texts:
            value = text.casefold()
            if any(word in value for word in ("dog", "canine", "puppy")):
                vector = (1., 0., 0., 0.)
            elif any(word in value for word in ("music", "piano", "melody")):
                vector = (0., 1., 0., 0.)
            elif any(word in value for word in ("archive", "backup")):
                vector = (0., 0., 1., 0.)
            else:
                vector = (0., 0., 0., 1.)
            rows.append(vector)
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        return rows


class TransformerIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = OfflineChatStore(":memory:")
        self.addCleanup(self.store.close)
        self.memory = ApprovedMemory(self.store,MODEL,TOKENIZER)
        self.encoders = []
        self.fail = False

        def factory(spec):
            enc = FixtureEncoder(spec, fail=self.fail)
            self.encoders.append(enc)
            return enc

        self.index = TransformerMemoryIndex(self.memory,encoder_factory=factory)
        self.addCleanup(self.index.close)
        self.spec = spec_for(self.temp.name)

    def add(self,label,text,kind="fact",**kwargs):
        return self.memory.save(kind=kind,label=label,text=text,tags=[],
                  source=None,expires_at=kwargs.pop("expires_at",None),approved=True,**kwargs)

    def install(self):
        return self.index.install(self.spec,approved=True)

    def refresh(self, **kwargs):
        return self.index.refresh(expected_encoder=self.spec.identity,approved=True,**kwargs)

    def test_uninstalled_search_never_loads_encoder(self):
        self.add("Archive","Archive backup")
        self.assertIsNone(self.index.status()["bank"])
        self.assertFalse(self.index.search("backup")["enabled"])
        self.assertEqual(self.encoders,[])

    def test_explicit_install_and_public_status_does_not_disclose_paths(self):
        with self.assertRaises(MemoryRejected):
            self.index.install(self.spec,approved=False)
        status = self.install()
        self.assertEqual(status["bank"]["encoder_identity"], self.spec.identity)
        self.assertNotIn("model_path",status["bank"])
        self.assertNotIn("tokenizer_path",status["bank"])
        self.assertFalse(status["semantic_quality_certified"])
        self.assertFalse(status["runtime_readiness_rechecked"])
        self.assertTrue(status["bank"]["prior_install_smoke"]["query_path_executed"])
        self.assertEqual(len(self.encoders),1)

    def test_fixture_semantic_synonym_and_kind_filter(self):
        canine = self.add("Dog","A dog prefers walks",kind="preference")
        piano = self.add("Music","Piano melody")
        self.install()
        self.assertEqual(self.refresh()["processed"],2)
        search = self.index.search("canine",limit=2)
        self.assertEqual(search["records"][0]["memory_id"],canine["memory_id"])
        self.assertEqual(search["records"][0]["cosine"],1.0)
        self.assertEqual(search["records"][1]["memory_id"],piano["memory_id"])
        self.assertTrue(search["exhaustive_vector_scan"])
        strict = self.index.search("canine",kinds=["fact"])
        self.assertEqual([r["memory_id"] for r in strict["records"]],[piano["memory_id"]])
        self.assertFalse(search["semantic_quality_certified"])
        self.assertFalse(search["remote_calls"])

    def test_index_keyset_pages_and_coverage(self):
        expected = {self.add("Note "+str(i),"Archive backup "+str(i))["memory_id"]
                    for i in range(7)}
        self.install()
        self.assertEqual(self.index.status()["indexed_active_memories"],0)
        cursor = None
        total = 0
        for _ in range(5):
            result = self.refresh(cursor=cursor,limit=2)
            total += result["processed"]
            cursor = result["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(total,7)
        self.assertIsNone(cursor)
        status = self.index.status()
        self.assertTrue(status["index_complete_snapshot"])
        self.assertEqual(status["indexed_active_memories"],7)
        found = {row["memory_id"] for row in self.index.search("backup",limit=20)["records"]}
        self.assertEqual(found,expected)

    def test_edit_excludes_stale_vector_until_explicit_refresh(self):
        original = self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        edited = self.add("Music","Piano melody",pin=pin(original))
        self.assertEqual(original["memory_id"],edited["memory_id"])
        self.assertEqual(self.index.status()["indexed_active_memories"],0)
        self.assertEqual(self.index.search("canine")["records"],[])
        self.refresh()
        result = self.index.search("melody")
        self.assertEqual(result["records"][0]["revision"],edited["revision"])
        self.assertEqual(result["records"][0]["sha256"],edited["sha256"])

    def test_deleted_note_cascades_derived_vector_and_buckets(self):
        row = self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        self.memory.delete(pin(row),approved=True)
        self.assertEqual(self.index.search("dog")["records"],[])
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM jeeves_transformer_vectors").fetchone()[0],0)
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM jeeves_transformer_buckets").fetchone()[0],0)

    def test_expired_note_is_not_retrieved(self):
        now=int(time.time())
        self.add("Temporary","Dog",expires_at=now+15)
        self.install()
        self.refresh()
        with patch("skeleton.app.jeeves_transformer_memory.time.time",return_value=now+20):
            self.assertEqual(self.index.search("dog")["records"],[])
            self.assertEqual(self.index.status()["active_memories"],0)

    def test_revision_conflict_during_encoder_pass_publishes_nothing(self):
        row = self.add("Dog","Dog walks")
        self.install()
        self.encoders[-1].callback = lambda: self.add("Music","Music melody",pin=pin(row))
        with self.assertRaises(MemoryConflict):
            self.refresh()
        self.assertEqual(self.index.status()["indexed_active_memories"],0)
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM jeeves_transformer_vectors").fetchone()[0],0)

    def test_failed_replacement_preserves_previous_bank_and_index(self):
        self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        replacement = spec_for(self.temp.name,model_sha256="f"*64)
        self.fail = True
        with self.assertRaises(EncoderUnavailable):
            self.index.install(replacement,approved=True,expected_prior=self.spec.identity)
        self.assertEqual(self.index.status()["bank"]["encoder_identity"],self.spec.identity)
        self.assertEqual(self.index.status()["indexed_active_memories"],1)
        self.assertEqual(self.index.search("dog")["records"][0]["cosine"],1.0)

    def test_stale_replace_remove_and_refresh_conflicts(self):
        self.install()
        replacement=spec_for(self.temp.name,threads=2)
        with self.assertRaises(MemoryConflict):
            self.index.install(replacement,approved=True)
        with self.assertRaises(MemoryConflict):
            self.index.uninstall("f"*64,approved=True)
        with self.assertRaises(MemoryConflict):
            self.index.refresh(expected_encoder="f"*64,approved=True)
        with self.assertRaises(MemoryRejected):
            self.index.uninstall(self.spec.identity,approved=False)

    def test_successful_replace_invalidates_old_vectors_and_removal_preserves_notes(self):
        row=self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        replacement=spec_for(self.temp.name,threads=2)
        old=self.encoders[-1]
        self.index.install(replacement,approved=True,expected_prior=self.spec.identity)
        self.assertTrue(old.closed)
        self.assertEqual(self.index.status()["indexed_active_memories"],0)
        self.index.refresh(expected_encoder=replacement.identity,approved=True)
        self.index.uninstall(replacement.identity,approved=True)
        self.assertIsNone(self.index.status()["bank"])
        self.assertEqual(self.memory.list()["records"][0]["memory_id"],row["memory_id"])

    def test_scope_isolation(self):
        own=self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        foreign_memory=ApprovedMemory(self.store,OTHER,TOKENIZER)
        foreign=TransformerMemoryIndex(foreign_memory,encoder_factory=FixtureEncoder)
        self.addCleanup(foreign.close)
        foreign_memory.save(kind="fact",label="Foreign",text="Dog private",tags=[],
                  expires_at=None,source=None,approved=True)
        self.assertIsNone(foreign.status()["bank"])
        foreign.install(self.spec,approved=True)
        foreign.refresh(expected_encoder=self.spec.identity,approved=True)
        self.assertEqual(len(foreign.search("dog")["records"]),1)
        self.assertNotEqual(foreign.search("dog")["records"][0]["memory_id"],own["memory_id"])
        self.assertEqual(self.index.search("dog")["records"][0]["memory_id"],own["memory_id"])

    def test_tampered_vector_fails_closed(self):
        self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        with self.store._transaction():
            self.store._db.execute("UPDATE jeeves_transformer_vectors SET vector_sha256=?",("0"*64,))
        with self.assertRaises(MemoryRejected):
            self.index.search("dog")

    def test_tampered_bucket_fails_closed(self):
        self.add("Dog","Dog walks")
        self.install()
        self.refresh()
        with self.store._transaction():
            self.store._db.execute("UPDATE jeeves_transformer_buckets SET signature=(signature+1)%256 WHERE band=0")
        with self.assertRaises(MemoryRejected):
            self.index.search("dog")

    def test_approximate_path_discloses_candidate_cap(self):
        for i in range(10):
            self.add("Dog "+str(i),"Dog walks")
        self.install()
        self.refresh()
        with patch("skeleton.app.jeeves_transformer_memory.MAX_CANDIDATES",3):
            result=self.index.search("canine",limit=10)
        self.assertEqual(result["candidate_method"],"multiprobe-lsh-then-cosine")
        self.assertFalse(result["exhaustive_vector_scan"])
        self.assertTrue(result["candidate_limit_reached"])
        self.assertLessEqual(result["scanned_vectors"],3)
        self.assertEqual(result["eligible_vectors"],10)

    def test_closed_queries_and_budgets(self):
        self.install()
        for query in ("", "x"*1025, "x\x00y"):
            with self.subTest(query=query[:20]), self.assertRaises(MemoryRejected):
                self.index.search(query)
        for limit in (True,0,21):
            with self.subTest(limit=limit), self.assertRaises(MemoryRejected):
                self.index.search("dog",limit=limit)
        with self.assertRaises(MemoryRejected):
            self.index.search("dog",kinds=["fact","fact"])
        with self.assertRaises(MemoryRejected):
            self.refresh(limit=65)


class EncoderCustodyTests(unittest.TestCase):
    def test_spec_identity_changes_with_pooling_and_length_not_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=spec_for(root)
            moved=spec_for(root/"moved")
            self.assertEqual(first.identity,moved.identity)
            self.assertNotEqual(first.identity,spec_for(root,pooling="cls").identity)
            self.assertNotEqual(first.identity,spec_for(root,max_length=32).identity)

    def test_spec_rejects_unbounded_or_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            for changes in ({"dimensions":1537},{"threads":True},{"max_length":513},
                            {"pooling":"arbitrary"},{"model_path":"relative.onnx"},{"extra":1}):
                with self.subTest(changes=changes), self.assertRaises(EncoderUnavailable):
                    spec_for(directory,**changes)

    def test_pinned_file_exact_bytes_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"asset"
            path.write_bytes(b"fixture")
            raw,_stamp=_read_pinned(path,sha(b"fixture"),1024)
            self.assertEqual(raw,b"fixture")
            with self.assertRaises(EncoderUnavailable):
                _read_pinned(path,"0"*64,1024)
            with self.assertRaises(EncoderUnavailable):
                _read_pinned(path,sha(b"fixture"),2)

    def test_reject_symlink_even_if_target_hash_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"asset"
            path.write_bytes(b"fixture")
            link=Path(directory)/"link"
            try:
                link.symlink_to(path)
            except (OSError,NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(EncoderUnavailable):
                _read_pinned(link,sha(b"fixture"),1024)


_OPTIONAL=("numpy","onnx","onnxruntime","tokenizers")
@unittest.skipUnless(all(importlib.util.find_spec(name) is not None for name in _OPTIONAL),
                     "optional local sentence encoder dependencies not installed")
class ActualSyntheticONNXTests(unittest.TestCase):
    """Runs true ONNX Runtime on a tiny deterministic graph, not pretrained weights."""

    def test_real_cpu_graph_and_index(self):
        import numpy as np
        import onnx
        from onnx import TensorProto, helper, numpy_helper
        from tokenizers import Tokenizer, models, pre_tokenizers
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            words=["[PAD]","[UNK]","local","encoder","integrity","probe",
                   "a","second","independent","sentence","dog","canine","music","piano"]
            table=np.zeros((len(words),4),dtype=np.float32)
            for idx,word in enumerate(words):
                channel=0 if word in ("local","encoder","integrity","probe","dog","canine") else 1
                table[idx,channel]=1.0
            graph=helper.make_graph(
                [helper.make_node("Gather",["word_vectors","input_ids"],["last_hidden_state"],axis=0)],
                "synthetic-fixture",[
                    helper.make_tensor_value_info("input_ids",TensorProto.INT64,["batch","seq"]),
                    helper.make_tensor_value_info("attention_mask",TensorProto.INT64,["batch","seq"]),
                ],[helper.make_tensor_value_info("last_hidden_state",TensorProto.FLOAT,["batch","seq",4])],
                [numpy_helper.from_array(table,name="word_vectors")])
            model=helper.make_model(graph,opset_imports=[helper.make_opsetid("",13)],ir_version=8)
            onnx.checker.check_model(model)
            model_data=model.SerializeToString()
            (root/"encoder.onnx").write_bytes(model_data)
            tok=Tokenizer(models.WordLevel({word:i for i,word in enumerate(words)},unk_token="[UNK]"))
            tok.pre_tokenizer=pre_tokenizers.Whitespace()
            token_data=tok.to_str().encode("utf-8")
            (root/"tokenizer.json").write_bytes(token_data)
            spec=spec_for(root,model_sha256=sha(model_data),tokenizer_sha256=sha(token_data))
            encoder=SentenceEncoder(spec)
            try:
                qualification=encoder.qualification()
                self.assertTrue(qualification["query_path_executed"])
                self.assertFalse(qualification["independent_quality_certified"])
                result=encoder.encode(["dog","canine","music"],query=True)
                self.assertEqual(len(result),3)
                self.assertGreater(sum(a*b for a,b in zip(result[0],result[1])),0.99)
                self.assertLess(sum(a*b for a,b in zip(result[0],result[2])),0.01)
                for vector in result:
                    self.assertTrue(math.isclose(sum(x*x for x in vector),1.0,abs_tol=1e-6))
                (root/"encoder.onnx").write_bytes(b"changed")
                with self.assertRaises(EncoderUnavailable):
                    encoder.encode(["dog"],query=True)
            finally:
                encoder.close()


if __name__=="__main__":
    unittest.main()
