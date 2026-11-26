"""Exact route parity, bounded work reuse, and evidence-only revision analytics."""
from __future__ import annotations

import hashlib
import unittest

from core.dragon_archive_intelligence import (
    ArchiveWork, archive_report, build_index_bundle, compare_text,
    eligible_material, rank_exact,
)
from core.dragon_hybrid_rank import Candidate, build_route, rank
from core.dragon_passage_index import build_passage_route, rank_passage_offsets
from skeleton.ai.webcrawler import dragon_archive_scale as archive
from skeleton.ai.webcrawler.dragon_archive_grant import create_grant

SCOPE={"owner_id":"archive-owner","tenant_id":"archive-tenant"}
NOW=1700000000


def make_fixture():
    text=("The spacecraft flight manual describes aerodynamics, propulsion, "
          "navigation, velocity, guidance, and engineering. ")*30
    changed=text.replace("velocity","trajectory",2)
    sources={}
    for i,body in enumerate((text,text,changed,"A separate gardening manual describes soil and irrigation.")):
        sid=hashlib.sha256(str(i).encode()).hexdigest()
        sources[sid]={"source_id":sid,"title":"Engineering reference" if i<3 else "Garden reference",
            "text":body,"preserved_text_hash":hashlib.sha256(body.encode()).hexdigest(),
            "canonical_url":"https://example.com/reference/"+str(i),"fetched_at":NOW-100+i,
            "provenance":{"source_status":"unreviewed_external_capture","training_permission":False,
                "http_freshness":{"private":False,"no_store":False,"sensitive_vary":False}}}
    snap={"snapshot_digest":"a"*64,"state":"completed","sources":sources,
        "binding":{"consent":{"source_rights_acknowledged":True}}}
    grant=create_grant(snapshot=snap,policies={},now=NOW,days=2)
    return snap,grant,text,changed


class ArchiveIntelligenceTests(unittest.TestCase):
    def test_unified_index_matches_three_existing_route_contracts(self):
        snap,grant,_,_=make_fixture()
        allowed=set(snap["sources"])
        expected=(archive.build_index(SCOPE,snap,grant,{},NOW,allowed),
                  build_route(SCOPE,snap,grant,{},NOW,allowed),
                  build_passage_route(SCOPE,snap,grant,{},NOW,allowed))
        work=ArchiveWork()
        actual=build_index_bundle(SCOPE,snap,grant,{},NOW,allowed,work=work)
        self.assertEqual(actual,expected)
        self.assertGreater(work.receipt()["hits"],0)

    def test_rank_and_passage_scores_are_identical_with_reuse(self):
        snap,grant,_,_=make_fixture()
        allowed=set(snap["sources"])
        terms,_=archive.query_terms(SCOPE,"flight navigation")
        work=ArchiveWork()
        exact=rank_exact(snap,grant,{},NOW,terms,allowed,work)
        self.assertEqual(exact,archive.rank_exact(SCOPE,snap,grant,{},NOW,terms,allowed))
        candidates=[Candidate(sid,s["title"],s["text"]) for sid,s in snap["sources"].items()]
        self.assertEqual(rank("flight navigation",candidates),rank("flight navigation",candidates,work=work))
        route=build_passage_route(SCOPE,snap,grant,{},NOW,allowed)
        expected=rank_passage_offsets(SCOPE,"flight navigation",snap,grant,{},NOW,route,allowed)
        self.assertEqual(expected,rank_passage_offsets(SCOPE,"flight navigation",snap,grant,{},NOW,route,allowed,work=work))
        self.assertGreater(work.receipt()["hits"],0)

    def test_policy_revocation_cannot_reuse_authority(self):
        snap,grant,_,_=make_fixture()
        allowed=set(snap["sources"])
        terms,_=archive.query_terms(SCOPE,"flight navigation")
        work=ArchiveWork()
        original=rank_exact(snap,grant,{},NOW,terms,allowed,work)
        self.assertTrue(original)
        sid=original[0]["source_id"]
        policies={sid:{"enabled":False,"version":1}}
        report=rank_exact(snap,grant,policies,NOW,terms,allowed,work)
        self.assertNotIn(sid,{x["source_id"] for x in report})
        self.assertEqual(rank_exact(snap,grant,{},NOW+3*86400,terms,allowed,work),[])

    def test_checksum_drift_held(self):
        snap,grant,_,_=make_fixture()
        sid=next(iter(snap["sources"]))
        snap["sources"][sid]["text"]+="modified"
        with self.assertRaises(ValueError):
            eligible_material(snap,grant,{},set(snap["sources"]),NOW)

    def test_analysis_preserves_exact_and_approximate_distinction(self):
        snap,grant,text,changed=make_fixture()
        material=eligible_material(snap,grant,{},set(snap["sources"]),NOW)
        report=archive_report(material,snapshot_digest=snap["snapshot_digest"],grant=grant)
        self.assertEqual(report["qualified_sources"],4)
        self.assertEqual(report["unique_texts"],3)
        self.assertEqual(report["exact_duplicate_bytes_estimate"],len(text.encode()))
        self.assertFalse(report["physical_storage_modified"])
        self.assertEqual(compare_text(text,text)["classification"],"identical")
        comparison=compare_text(text,changed)
        self.assertNotEqual(comparison["classification"],"identical")
        self.assertTrue(comparison["near_duplicate_is_advisory"])
        self.assertGreater(comparison["reusable_chunk_bytes_estimate"],0)

    def test_weighted_lru_and_no_persistent_authority(self):
        work=ArchiveWork(max_entries=2,max_weight=1024*1024)
        for i in range(5):
            work.exact_counts("title",f"body {i}")
        receipt=work.receipt()
        self.assertEqual(receipt["resident_entries"],2)
        self.assertEqual(receipt["evictions"],3)
        self.assertFalse(receipt["persistent"])


if __name__=="__main__":
    unittest.main()
