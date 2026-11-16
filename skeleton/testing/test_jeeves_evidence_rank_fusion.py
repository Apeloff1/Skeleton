"""Local retrieval fusion tests with synthetic rank channels, no vector provider."""
import unittest
from dataclasses import replace
from hashlib import sha256

from skeleton.ai.runtime.inference.evidence_packing import Excerpt,Scope
from skeleton.ai.runtime.inference.evidence_rank_fusion import (
    RankedChannel,rerank,prepare_ranked_request,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest,LocalInputBudget


def pin(s):
    return sha256(s.encode()).hexdigest()


def row(label,text,stance="supports",claim="topic",start=0,end=None):
    return Excerpt(pin(label+"source"),pin(label+"revision"),pin(text),
                   pin(label+"family"),pin(claim),stance,text,5000,9000,start,end)


def scope(q=None):
    return Scope(pin("owner"),pin("model"),pin("tokenizer"),pin("snapshot"),q or pin("request"),100)


class EvidenceRankFusionTests(unittest.TestCase):
    def setUp(self):
        self.a=row("a","KV cache quantization reduces memory usage.")
        self.b=row("b","Gardening and weather patterns.")
        self.c=row("c","Quantization may degrade output quality.",stance="contradicts")
        self.sc=scope()
        self.q="KV cache quantization"

    def run_rank(self,rows,**kwargs):
        defaults=dict(scope=self.sc,query_text_sha256=pin(self.q),
                      revoked_sources=frozenset(),revoked_revisions=frozenset())
        defaults.update(kwargs)
        return rerank(self.q,rows,**defaults)

    def test_lexical_rank_and_unchanged_source(self):
        result=self.run_rank([self.b,self.a,self.c])
        self.assertEqual(result.ranked[0].identity,self.a.identity)
        self.assertEqual(result.ranked[0].text,self.a.text)
        self.assertEqual(result.lexical_matched,2)
        self.assertEqual(result.channel_count,0)

    def test_high_weight_semantic_rank_can_recover_lexical_miss(self):
        channel=RankedChannel(self.sc.identity,pin("semantic"),(self.b.identity,),4)
        result=self.run_rank([self.a,self.b,self.c],channels=(channel,))
        self.assertEqual(result.ranked[0].identity,self.b.identity)

    def test_revoked_and_historical_sources_removed_even_if_ranked(self):
        old=row("old","KV cache",end=100)
        channel=RankedChannel(self.sc.identity,pin("semantic"),(self.b.identity,old.identity),4)
        result=self.run_rank([self.a,self.b,old],channels=(channel,),
                             revoked_sources=frozenset((self.b.source_sha256,)))
        self.assertEqual(tuple(x.identity for x in result.ranked),(self.a.identity,))
        self.assertEqual(dict(result.excluded)[self.b.identity],"revoked")
        self.assertEqual(dict(result.excluded)[old.identity],"outside_as_of")

    def test_foreign_or_unknown_channels_refused(self):
        for c in (RankedChannel(pin("stale"),pin("channel"),(self.a.identity,)),
                  RankedChannel(self.sc.identity,pin("channel"),(pin("unknown"),))):
            with self.assertRaises(ValueError):
                self.run_rank([self.a],channels=(c,))

    def test_permutation_determinism(self):
        a=self.run_rank([self.a,self.b,self.c])
        b=self.run_rank([self.c,self.a,self.b])
        self.assertEqual(a.receipt_sha256,b.receipt_sha256)

    def test_conflicting_rows_not_truncated(self):
        result=self.run_rank([self.a,self.b,self.c])
        self.assertEqual({x.identity for x in result.ranked},
                         {x.identity for x in (self.a,self.b,self.c)})

    def test_query_digest_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            self.run_rank([self.a],query_text_sha256=pin("other"))

    def test_duplicate_channels_denied(self):
        c=RankedChannel(self.sc.identity,pin("channel"),(self.a.identity,))
        with self.assertRaises(ValueError):
            self.run_rank([self.a],channels=(c,c))

    def test_fusion_and_packing_preserve_conflicts(self):
        request=LocalInferenceRequest(self.q,max_output_tokens=64)
        prepared,packing,rank=prepare_ranked_request(
            request,scope=scope(request.digest),excerpts=(self.a,self.c),
            budget=LocalInputBudget(4096,128,4096),
            count_request=lambda r:len(r.rendered_input.encode()),
            required_claims=(self.a.claim_sha256,),revoked_sources=frozenset(),
            revoked_revisions=frozenset())
        self.assertIsNotNone(prepared)
        self.assertTrue(packing.complete)
        self.assertEqual({x.stance for x in packing.selected},{"supports","contradicts"})
        self.assertEqual(rank.lexical_matched,2)
        self.assertIsNone(prepared.context_digest)

if __name__=="__main__":
    unittest.main()
