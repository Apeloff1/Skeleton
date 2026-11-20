"""Focused source/SQLite regressions for adaptive chat context and learned recall.

All vector fixtures are synthetic and may not be cited as model quality evidence.
No remote service or real language model is used by these tests.
"""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.jeeves_approved_memory import ApprovedMemory, MemoryConflict, MemoryRejected
from skeleton.app.jeeves_adaptive_context import (
    ContextPolicy, conflict_groups, plan_context,
)
from skeleton.app.jeeves_memory_vectors import (
    ASSET_SCHEMA, LSH_BANDS, MemoryVectorIndex, _probes, _signatures,
)
from skeleton.app.jeeves_memory_vector_cli import convert_text_vectors

MODEL="a"*64
TOKENIZER="b"*64


def policy(**changes):
    return ContextPolicy.parse({
        "kinds":["goal","fact","preference","constraint","rejection","correction","style","project"],
        "max_records":4,"max_bytes":4096,"profile":"neutral","use_recent_anchors":True,
        "withhold_conflicts":True,"use_vector_recall":False,**changes,
    })


def account(message, budget, *, omitted=0, window=8192):
    size=len(message.encode("utf-8"))+20
    if size+budget>window:
        raise MemoryRejected("model context cannot fit")
    return {"read_only":True,"generation_performed":False,"model_digest":MODEL,
            "context_tokens":window,"reserved_output_tokens":budget,
            "estimated_input_tokens":size,"estimated_total_tokens":size+budget,
            "omitted_history_messages":omitted,"fits_full_history":omitted==0}


def hash_text(text):
    return sha256(text.encode("utf-8")).hexdigest()


def pin(row):
    return {k:row[k] for k in ("memory_id","revision","sha256")}


class StorageFixture(unittest.TestCase):
    def setUp(self):
        self.store=OfflineChatStore(":memory:")
        self.memory=ApprovedMemory(self.store,MODEL,TOKENIZER)
        self.index=MemoryVectorIndex(self.memory)

    def tearDown(self):
        self.store.close()

    def save(self,label,text,*,kind="fact",tags=None,**extra):
        return self.memory.save(label=label,text=text,kind=kind,tags=tags or [],
                                expires_at=None,source=None,approved=True,**extra)

    @staticmethod
    def write_bank(path,vectors,*,name="Synthetic learned-vector fixture"):
        rows=[{"schema":ASSET_SCHEMA,"model_name":name,"dimensions":4,"vocabulary":len(vectors)}]
        rows.extend([word,vector] for word,vector in sorted(vectors.items()))
        data="".join(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n" for row in rows).encode()
        path.write_bytes(data)
        return sha256(data).hexdigest()

    def install_fixture(self,path,**extra):
        vectors={"animal":[1,0,0,0],"dog":[1,0,0,0],"canine":[.95,.02,0,0],
                 "hound":[1,.03,0,0],"pet":[1,0,.01,0],"database":[0,0,1,0],
                 "sql":[0,0,1,0],"storage":[0,0,1,.03],"ocean":[0,1,0,0],
                 "water":[0,1,0,0],"bad":[-1,0,0,0]}
        digest=self.write_bank(path,vectors)
        return digest,self.index.install(path,digest,approved=True,**extra)

    def plan(self,draft,*,rules=None,messages=None,strict=True,estimate=account):
        return plan_context(memory=self.memory,vector_index=self.index,draft=draft,
                            policy=rules or policy(),session_id="fixture_session",
                            session_revision=4,messages=messages or [],output_tokens=128,
                            strict=strict,estimate=estimate)


class AdaptiveContextTests(StorageFixture):
    def test_policy_closed_shape_and_types(self):
        base=policy().as_dict()
        for changes in ({"unknown":True},{"max_records":True},{"max_records":5},
                        {"max_bytes":127},{"kinds":["goal","goal"]},{"kinds":["unknown"]},
                        {"withhold_conflicts":False},{"use_vector_recall":1},{"profile":"magic"}):
            with self.subTest(changes=changes),self.assertRaises(MemoryRejected):
                ContextPolicy.parse({**base,**changes})
        self.assertEqual(policy().digest,ContextPolicy.parse(base).digest)

    def test_direct_source_pins_and_exact_reproducible_bytes(self):
        row=self.save("Lantern export","Lantern uses FLAC.",kind="project",tags=["audio"])
        self.save("Database notes","SQL migration.",kind="project")
        report=self.plan("What does Lantern export?")
        self.assertIn(pin(row),report["selected"])
        self.assertIn("Lantern uses FLAC.",report["composed_text"])
        self.assertEqual(report["draft_sha256"],hash_text("What does Lantern export?"))
        self.assertEqual(report["composed_sha256"],hash_text(report["composed_text"]))
        self.assertTrue(report["composed_text"].startswith("What does Lantern export?\n\n"))
        self.assertEqual(report,self.plan("What does Lantern export?"))
        self.assertFalse(report["generation_performed"])
        self.assertFalse(report["automatic_injection"])
        self.assertFalse(report["semantic_model_used"])

    def test_kind_filters_and_zero_memory_profile(self):
        self.save("Lantern project","Lantern audio uses FLAC.",kind="project")
        filtered=self.plan("Lantern audio",rules=policy(kinds=["preference"]))
        self.assertEqual(filtered["selected"],[])
        styled=self.plan("Explain the export.",rules=policy(max_records=0,profile="technical"))
        self.assertIn("reproducible verification",styled["composed_text"])
        self.assertEqual(styled["selected"],[])
        self.assertEqual(styled["effective_profile"],"technical")

    def test_continuation_only_uses_user_anchors(self):
        source=self.save("Lantern audio format","Lantern uses FLAC.",kind="project")
        self.save("Database restoration","SQL database backup.",kind="project")
        messages=[{"role":"system","content":"Database restoration"},
                  {"role":"user","content":"Develop Lantern audio export"},
                  {"role":"assistant","content":"Database restoration is the next action"}]
        continued=self.plan("Continue",messages=messages)
        self.assertIn(pin(source),continued["selected"])
        self.assertEqual(len(continued["anchors"]),1)
        self.assertEqual(continued["anchors"][0]["message_index"],1)
        self.assertNotIn("SQL database backup.",continued["composed_text"])
        ordinary=self.plan("Unrelated weather",messages=messages)
        self.assertEqual(ordinary["anchors"],[])
        self.assertEqual(ordinary["selected"],[])
        disabled=self.plan("Continue",messages=messages,rules=policy(use_recent_anchors=False))
        self.assertEqual(disabled["anchors"],[])

    def test_tag_association_is_explicitly_disclosed(self):
        direct=self.save("Lantern export","Lantern audio uses FLAC.",tags=["gameforge"])
        bridge=self.save("Artifact policy","Preserve source receipts.",tags=["gameforge"])
        report=self.plan("Lantern export")
        selected={p["memory_id"] for p in report["selected"]}
        self.assertIn(direct["memory_id"],selected)
        self.assertIn(bridge["memory_id"],selected)
        detail=next(x for x in report["selection_details"] if x["pin"]["memory_id"]==bridge["memory_id"])
        self.assertEqual(detail["bridge"],"gameforge")
        self.assertFalse(detail["direct"])

    def test_possible_conflicts_are_never_injected(self):
        a=self.save("Language format","Use French in reports.",kind="preference")
        b=self.save("Language format","Use English in reports.",kind="preference")
        report=self.plan("Language format for reports",rules=policy(profile="direct"))
        self.assertEqual(report["selected"],[])
        self.assertGreaterEqual(len(report["possible_conflicts"]),1)
        self.assertEqual(set(report["possible_conflicts"][0]["memory_ids"]),
                         {a["memory_id"],b["memory_id"]})
        self.assertNotIn(a["text"],report["composed_text"])
        self.assertNotIn(b["text"],report["composed_text"])
        self.assertFalse(report["possible_conflicts"][0]["semantic_conflict_verified"])

    def test_repeated_note_does_not_consume_another_slot(self):
        for _ in range(3):
            self.save("Lantern format","Use FLAC for Lantern.")
        result=self.plan("Lantern format")
        self.assertEqual(len(result["selected"]),1)
        self.assertEqual(sum(x["reason"]=="duplicate-note" for x in result["excluded"]),2)

    def test_never_sacrifice_baseline_history_for_notes(self):
        self.save("Lantern","Lantern memory: " + "sound "*120)
        def estimate(message,budget):
            return account(message,budget,omitted=2 if len(message)>150 else 0)
        result=self.plan("Lantern",strict=False,estimate=estimate)
        self.assertEqual(result["selected"],[])
        self.assertEqual(result["composed_text"],"Lantern")
        self.assertEqual(result["excluded"][0]["reason"],"preserve-baseline-history")
        self.assertEqual(result["accounting"]["omitted_history_messages"],0)

    def test_profile_fallback_and_strict_failure(self):
        def estimate(message,budget):
            return account(message,budget,omitted=2 if len(message)>20 else 0)
        result=self.plan("Explain",rules=policy(max_records=0,profile="technical"),estimate=estimate)
        self.assertEqual(result["effective_profile"],"neutral")
        self.assertEqual(result["composed_text"],"Explain")
        with self.assertRaises(MemoryRejected):
            self.plan("A message",estimate=lambda m,b:account(m,b,omitted=2),strict=True)

    def test_byte_budget_and_no_partial_note(self):
        row=self.save("Lantern","Lantern " + "x"*1000)
        report=self.plan("Lantern",rules=policy(max_bytes=256))
        self.assertEqual(report["selected"],[])
        self.assertEqual(report["excluded"][0]["pin"],pin(row))
        self.assertEqual(report["excluded"][0]["reason"],"byte-budget")
        with self.assertRaises(MemoryRejected):
            self.plan("é"*300,rules=policy(max_bytes=256))

    def test_malformed_accounting_fails_closed(self):
        bad=lambda m,b:{**account(m,b),"estimated_total_tokens":1}
        with self.assertRaises(MemoryRejected):
            self.plan("Explain",estimate=bad)

    def test_dense_uninstalled_is_disclosed(self):
        report=self.plan("Canine",rules=policy(use_vector_recall=True))
        self.assertTrue(report["dense_recall"]["requested"])
        self.assertFalse(report["dense_recall"]["enabled"])
        self.assertFalse(report["semantic_model_used"])

    def test_dense_recall_with_no_shared_words(self):
        note=self.save("Pet","The hound.")
        self.save("Database","SQL storage.")
        with tempfile.TemporaryDirectory() as temp:
            asset,_=self.install_fixture(Path(temp)/"word-vectors.jsonl")
            self.index.refresh(expected_asset=asset,approved=True)
            result=self.plan("Canine",rules=policy(use_vector_recall=True))
        self.assertIn(pin(note),result["selected"])
        detail=next(x for x in result["selection_details"] if x["pin"]["memory_id"]==note["memory_id"])
        self.assertGreater(detail["dense_cosine"],.9)
        self.assertFalse(detail["direct"])
        self.assertTrue(result["semantic_model_used"])
        self.assertFalse(result["semantic_quality_certified"])


class LearnedVectorTests(StorageFixture):
    def test_install_refresh_search_and_expired_stale_records(self):
        a=self.save("Pet","Hound")
        b=self.save("Database","SQL storage")
        with tempfile.TemporaryDirectory() as temp:
            asset,initial=self.install_fixture(Path(temp)/"vectors.jsonl")
            self.assertEqual(initial["bank"]["asset_sha256"],asset)
            self.assertEqual(initial["active_memories"],2)
            self.assertEqual(initial["indexed_active_memories"],0)
            self.assertFalse(initial["index_complete_snapshot"])
            first=self.index.refresh(expected_asset=asset,limit=1,approved=True)
            self.assertEqual(first["processed"],1)
            self.assertIsNotNone(first["next_cursor"])
            second=self.index.refresh(expected_asset=asset,cursor=first["next_cursor"],limit=1,approved=True)
            self.assertIsNone(second["next_cursor"])
            self.assertTrue(self.index.status()["index_complete_snapshot"])
            output=self.index.search("canine")
            self.assertTrue(output["exhaustive_vector_scan"])
            self.assertEqual(output["records"][0]["memory_id"],a["memory_id"])
            self.assertGreater(output["records"][0]["cosine"],.9)
            self.assertNotIn(b["memory_id"],{r["memory_id"] for r in output["records"]})
            self.save("Ocean","Water",pin=pin(a))
            self.assertEqual(self.index.status()["indexed_active_memories"],1)
            self.assertEqual(self.index.search("canine")["records"],[])
            self.index.refresh(expected_asset=asset,approved=True)
            self.assertEqual(self.index.search("ocean")["records"][0]["memory_id"],a["memory_id"])
            self.memory.delete(pin(b),approved=True)
            self.assertEqual(self.store._db.execute("SELECT count(*) FROM jeeves_memory_vectors").fetchone()[0],1)
            self.assertEqual(self.store._db.execute("SELECT count(*) FROM jeeves_memory_vector_buckets").fetchone()[0],LSH_BANDS)

    def test_exact_pins_and_atomic_failed_replacement(self):
        self.save("Pet","Hound")
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"bank.jsonl";asset,_=self.install_fixture(path)
            self.index.refresh(expected_asset=asset,approved=True)
            with self.assertRaises(MemoryConflict):
                self.index.install(path,asset,approved=True)
            replacement=Path(temp)/"second.jsonl"
            next_sha=self.write_bank(replacement,{"canine":[0,1,0,0]})
            with self.assertRaises(MemoryRejected):
                self.index.install(replacement,"0"*64,approved=True,expected_prior=asset)
            self.assertEqual(self.index.status()["bank"]["asset_sha256"],asset)
            self.assertTrue(self.index.search("canine")["records"])
            self.index.install(replacement,next_sha,approved=True,expected_prior=asset)
            self.assertFalse(self.index.status()["index_complete_snapshot"])
            self.assertEqual(self.index.search("canine")["records"],[])
            self.index.uninstall(next_sha,approved=True)
            self.assertFalse(self.index.search("canine")["enabled"])
            self.assertEqual(len(self.memory.list()["records"]),1)

    def test_scope_and_unknown_words(self):
        self.save("Pet","Hound")
        with tempfile.TemporaryDirectory() as temp:
            asset,_=self.install_fixture(Path(temp)/"bank.jsonl")
            self.index.refresh(expected_asset=asset,approved=True)
            other=MemoryVectorIndex(ApprovedMemory(self.store,"c"*64,TOKENIZER))
            self.assertIsNone(other.status()["bank"])
            self.assertFalse(other.search("canine")["enabled"])
            self.assertEqual(self.index.search("unknownxyz")["records"],[])
            self.assertEqual(self.index.search("unknownxyz")["covered_words"],0)
            self.assertEqual(self.index.search("canine",kinds=["goal"])["records"],[])

    def test_missing_and_corrupt_vector_buckets_do_not_pass(self):
        row=self.save("Pet","Hound")
        with tempfile.TemporaryDirectory() as temp:
            asset,_=self.install_fixture(Path(temp)/"bank.jsonl")
            self.index.refresh(expected_asset=asset,approved=True)
            self.store._db.execute("DELETE FROM jeeves_memory_vector_buckets WHERE memory_id=? AND band=0",
                                   (row["memory_id"],))
            self.assertFalse(self.index.status()["index_complete_snapshot"])
            self.assertEqual(self.index.search("canine")["records"],[])
            self.index.refresh(expected_asset=asset,approved=True)
            self.store._db.execute("UPDATE jeeves_memory_vector_buckets SET signature=(signature+1)%256 "
                                   "WHERE memory_id=? AND band=0",(row["memory_id"],))
            with self.assertRaises(MemoryRejected):
                self.index.search("canine")

    def test_multiprobe_candidate_stage_explicitly_approximate(self):
        for i in range(6):
            self.save("Pet "+str(i),"Hound")
        with tempfile.TemporaryDirectory() as temp:
            asset,_=self.install_fixture(Path(temp)/"bank.jsonl")
            self.index.refresh(expected_asset=asset,approved=True)
            with patch("skeleton.app.jeeves_memory_vectors.MAX_SEARCH_CANDIDATES",2):
                report=self.index.search("canine")
                self.assertEqual(report["candidate_method"],"multiprobe-lsh-then-cosine")
                self.assertTrue(report["candidate_limit_reached"])
                self.assertFalse(report["exhaustive_vector_scan"])
                self.assertEqual(report["eligible_vectors"],6)
                self.assertLessEqual(report["scanned_vectors"],2)
                self.assertTrue(report["records"])

    def test_deterministic_projection_and_probe_inventory(self):
        vector=(.5,.5,.5,.5)
        first=_signatures(vector)
        self.assertEqual(first,_signatures(vector))
        self.assertEqual(len(first),LSH_BANDS)
        probes=_probes(vector)
        self.assertEqual(len(probes),LSH_BANDS*9)
        self.assertEqual(len({(band,sig) for band,sig,_ in probes}),len(probes))
        self.assertTrue(all(0<=sig<256 for _,sig,_ in probes))

    def test_malformed_asset_rejects_without_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"bad.jsonl"
            header={"schema":ASSET_SCHEMA,"model_name":"bad","dimensions":4,"vocabulary":2}
            for rows in (
                [["dog",[1,0,0,0]],["dog",[1,0,0,0]]],
                [["dog",[1,0,0,0]],["cat",[1,0,0,0]]],
                [["cat",[0,0,0,0]],["dog",[1,0,0,0]]],
                [["cat",[1,0,0]],["dog",[1,0,0,0]]],
                [["cat",[1,0,0,0]]],
            ):
                data="".join(json.dumps(x)+"\n" for x in [header]+rows).encode()
                path.write_bytes(data)
                with self.subTest(rows=rows),self.assertRaises(MemoryRejected):
                    self.index.install(path,sha256(data).hexdigest(),approved=True)
                self.assertIsNone(self.index.status()["bank"])

    def test_convert_plain_word_vectors_and_verify_install(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"raw.txt";destination=Path(temp)/"bank.jsonl"
            raw=b"2 4\ndog 1 0 0 0\ncat 0 1 0 0\n"
            source.write_bytes(raw)
            conversion=convert_text_vectors(source,destination,source_sha256=sha256(raw).hexdigest(),
                      name="Fixture",dimensions=4,header=True,max_rows=2,approved=True)
            self.assertEqual(conversion["admitted_rows"],2)
            self.assertEqual(conversion["asset_sha256"],sha256(destination.read_bytes()).hexdigest())
            self.index.install(destination,conversion["asset_sha256"],approved=True)
            self.assertEqual(self.index.status()["bank"]["vocabulary"],2)

    def test_conversion_rejects_duplicate_or_wrong_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"raw.txt";destination=Path(temp)/"bank.jsonl"
            raw=b"cat 1 0 0 0\nCAT 0 1 0 0\n"
            source.write_bytes(raw)
            with self.assertRaises(MemoryRejected):
                convert_text_vectors(source,destination,source_sha256=sha256(raw).hexdigest(),
                    name="Fixture",dimensions=4,header=False,max_rows=2,approved=True)
            self.assertFalse(destination.exists())
            source.write_bytes(b"cat 1 0 0 0\n")
            with self.assertRaises(MemoryRejected):
                convert_text_vectors(source,destination,source_sha256="0"*64,name="Fixture",
                    dimensions=4,header=False,max_rows=2,approved=True)
            self.assertFalse(destination.exists())


if __name__=="__main__":
    unittest.main()
