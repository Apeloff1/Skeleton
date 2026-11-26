"""Real SQLite regressions for streaming reference custody and grounded ranking."""
from __future__ import annotations

import math
import unicodedata
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.app.offline_knowledge import (
    OfflineKnowledgeLibrary, LocalKnowledgeHit, _diverse_grounding_hits, _terms, _TERMS,
)


class StreamingReferenceTests(unittest.TestCase):
    def setUp(self):
        self.store=OfflineChatStore(":memory:")
        self.addCleanup(self.store.close)
        self.library=OfflineKnowledgeLibrary(self.store,"a"*64,"b"*64)
        p=patch("skeleton.app.offline_knowledge._require_local_headroom")
        self.pressure=p.start()
        self.addCleanup(p.stop)

    def add(self,title,text):
        return self.library.add_text(title,text)["document_id"]

    def fixture(self):
        a=self.add("first","local rendering alpha rasterizer " * 40+" unique tail")
        b=self.add("second","local shader beta local rendering " * 20+" contrast")
        c=self.add("unrelated","distant weather patterns and rain")
        return a,b,c

    def reference_rank(self,query,limit=6,ids=None):
        # Independent legacy materialized ranking for arithmetic comparison.
        _,records=self.library._verified_snapshot()
        if ids is not None:
            records=[row for row in records if row[0] in ids]
        terms=_terms(query)
        q=unicodedata.normalize("NFKC",query.strip()).casefold()
        df={x:0 for x in terms}
        pairs=[]
        for row in records:
            text=unicodedata.normalize("NFKC",row[6]).casefold()
            freq={}
            for x in _TERMS.findall(text):
                if x in df:
                    freq[x]=freq.get(x,0)+1
            for x in freq:
                df[x]+=1
            pairs.append((text,freq,row))
        hits=[]
        for text,freq,row in pairs:
            if not freq:
                continue
            score=sum((1+math.log1p(freq[token]))*
                      math.log1p((len(records)+1)/(df[token]+.5)) for token in sorted(freq))
            if q in text:
                score+=2.
            hits.append(LocalKnowledgeHit(*row,score))
        return [x.to_dict() for x in sorted(hits,key=lambda x:(-x.score,x.document_id,x.chunk_index))[:limit]]

    def test_search_matches_materialized_reference_rank(self):
        a,b,_=self.fixture()
        for scope in (None,(a,),(a,b)):
            for query in ("local rendering","rasterizer","shader rendering","weather","absent"):
                with self.subTest(scope=scope,query=query):
                    self.assertEqual(self.library.search(query,limit=3,document_ids=scope),
                                     self.reference_rank(query,limit=3,ids=scope))

    def test_actual_public_search_does_not_materialize_corpus(self):
        self.fixture()
        with patch.object(self.library,"_verified_snapshot",side_effect=AssertionError("full corpus materialized")):
            hits=self.library.search("rendering",limit=2)
        self.assertEqual(len(hits),2)

    def test_add_list_get_and_duplicate_no_legacy_materialization(self):
        with patch.object(self.library,"_verified_snapshot",side_effect=AssertionError("full corpus materialized")):
            a=self.library.add_text("first","local renderer alpha "*100)
            b=self.library.add_text("same existing","local renderer alpha "*100)
            self.assertTrue(b["reused"])
            self.assertEqual(a["document_id"],b["document_id"])
            self.assertEqual(a["chunk_count"],b["chunk_count"])
            self.assertEqual(self.library.list_documents()[0]["document_id"],a["document_id"])
            self.assertEqual(self.library.get_document(a["document_id"])["text"],
                             "local renderer alpha "*100)

    def test_scope_does_not_hide_corrupted_unselected_source(self):
        a,b,_=self.fixture()
        self.store._db.execute("UPDATE offline_documents SET content_text=? WHERE document_id=?",
                               ("mutated",b))
        with self.assertRaisesRegex(RuntimeContractError,"hash mismatch"):
            self.library.search("local",document_ids=(a,))

    def test_deleted_selected_source_no_global_fallback(self):
        a,_,_=self.fixture()
        self.library.delete(a)
        with self.assertRaisesRegex(RuntimeContractError,"selected local grounding source"):
            self.library.search("local",document_ids=(a,))

    def test_missing_chunk_rejected_before_ranking(self):
        a,_,_=self.fixture()
        self.store._db.execute("DELETE FROM offline_document_chunks WHERE document_id=? AND ordinal=0",(a,))
        with self.assertRaises(RuntimeContractError):
            self.library.search("local")

    def test_extra_chunk_rejected(self):
        a=self.add("a","local renderer reference")
        self.store._db.execute("INSERT INTO offline_document_chunks VALUES (?,?,?,?,?)",
                               (a,100,0,5,"local"))
        with self.assertRaisesRegex(RuntimeContractError,"extra passages"):
            self.library.get_document(a)

    def test_mutated_index_passage_rejected_before_ranking(self):
        a,_,_=self.fixture()
        self.store._db.execute("UPDATE offline_document_chunks SET content=? WHERE document_id=? AND ordinal=0",
                               ("invented",a))
        with self.assertRaisesRegex(RuntimeContractError,"provenance mismatch"):
            self.library.search("local")

    def test_model_and_tokenizer_scope_remains_separate(self):
        a=self.add("here","local renderer")
        other=OfflineKnowledgeLibrary(self.store,"c"*64,"b"*64)
        b=other.add_text("other","local renderer second")["document_id"]
        self.assertEqual({x["document_id"] for x in self.library.search("renderer")},{a})
        with self.assertRaises(RuntimeContractError):
            self.library.search("renderer",document_ids=(b,))

    def test_headroom_checked_per_document_not_corpus_sum(self):
        self.fixture()
        self.pressure.reset_mock()
        self.library.search("renderer")
        calls=[c.args[0] for c in self.pressure.call_args_list]
        self.assertGreaterEqual(len(calls),3)
        total=self.store._db.execute("SELECT SUM(LENGTH(CAST(content_text AS BLOB))) FROM offline_documents").fetchone()[0]
        self.assertLess(max(calls),total*2)

    def test_snapshot_rollback_after_consumer_error(self):
        self.fixture()
        with patch.object(self.library,"_verified_search_pass",side_effect=RuntimeError("fault")):
            with self.assertRaises(RuntimeError):
                self.library.search("local")
        self.assertFalse(self.store._db.in_transaction)
        self.assertTrue(self.library.search("local"))

    def test_only_one_full_source_verification_pass(self):
        self.fixture()
        with patch.object(self.library,"_verified_search_pass",
                          wraps=self.library._verified_search_pass) as calls:
            self.library.search("local rendering")
        self.assertEqual(calls.call_count,1)

    def test_unicode_citation_bytes_preserved(self):
        text="Norsk gjengivelse: blå skjerm, æ ø å. fullbredde Ａ."
        doc=self.add("Norsk",text)
        hit=self.library.search("blå skjerm")[0]
        self.assertEqual(hit["document_id"],doc)
        self.assertEqual(hit["passage"],text)

    def test_invalid_diversity_flag_rejected(self):
        with self.assertRaises(RuntimeContractError):
            self.library.search("local",diversify=1)


def hit(doc,idx,text,score,start=0,end=None):
    return LocalKnowledgeHit(doc,"source","a"*64,idx,start,end or start+len(text),text,score)


class GroundingDiversityTests(unittest.TestCase):
    def test_clear_dup_replaced_only_by_relevant_alternative(self):
        a=hit("a",0,"identical source passage",10)
        b=hit("b",0,a.passage,9)
        c=hit("c",0,"independent useful evidence",8)
        self.assertEqual(_diverse_grounding_hits([a,b,c],2),[a,c])

    def test_weak_alternative_never_displaces_top_match(self):
        a=hit("a",0,"duplicate",10)
        b=hit("b",0,"duplicate",9)
        c=hit("c",0,"weak",1)
        self.assertEqual(_diverse_grounding_hits([a,b,c],2),[a,b])

    def test_negation_preserved_across_sources(self):
        a=hit("a",0,"Feature is supported",10)
        b=hit("b",0,"Feature is not supported",9)
        c=hit("c",0,"Another feature",8)
        self.assertEqual(_diverse_grounding_hits([a,b,c],2),[a,b])

    def test_exact_offset_overlap_can_trigger_diversity(self):
        a=hit("a",0,"passage one",10,0,100)
        b=hit("a",1,"passage two",9,10,110)
        c=hit("c",0,"independent",8)
        self.assertEqual(_diverse_grounding_hits([a,b,c],2),[a,c])

    def test_single_result_keeps_exact_best(self):
        a=hit("a",0,"best",10)
        b=hit("b",0,"another",9)
        self.assertEqual(_diverse_grounding_hits([a,b],1),[a])

if __name__=="__main__":
    unittest.main()
