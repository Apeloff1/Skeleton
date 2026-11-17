"""Ten objectives share exact source authority checks and feature computation."""
from __future__ import annotations

import unittest

from core import dragon_archive_matrix as matrix
from core.dragon_archive_intelligence import ArchiveWork,rank_exact
from skeleton.ai.webcrawler import dragon_archive_scale as a
from test_dragon_archive_intelligence import make_fixture,SCOPE,NOW

QUERIES=["flight navigation","propulsion","velocity","trajectory","engineering",
         "gardening soil","irrigation","manual","aerodynamics","guidance"]


class ArchiveMatrixTests(unittest.TestCase):
    def test_ten_objective_equivalence_and_source_pass_reduction(self):
        snap,grant,_,_=make_fixture();allowed=set(snap["sources"])
        prepared=matrix.prepare(SCOPE,QUERIES)
        work=ArchiveWork()
        actual,checks=matrix.evaluate(snap,grant,{},allowed,NOW,prepared,work)
        self.assertEqual(checks,len(allowed))
        self.assertEqual(work.receipt()["requests"],len(allowed))
        self.assertGreater(work.receipt()["hits"],0)
        baseline=ArchiveWork()
        for q,p in zip(QUERIES,prepared):
            terms,_=a.query_terms(SCOPE,q)
            expected=rank_exact(snap,grant,{},NOW,terms,allowed,baseline)
            found={r["source_id"]:next(x for x in r["objectives"] if x["objective_id"]==p["id"])
                   for r in actual if any(x["objective_id"]==p["id"] for x in r["objectives"])}
            self.assertEqual(set(found),{x["source_id"] for x in expected})
            for hit in expected:
                self.assertEqual(found[hit["source_id"]]["matched_terms"],hit["matched_terms"])
                self.assertEqual(found[hit["source_id"]]["term_frequency"],hit["term_frequency"])
        self.assertEqual(baseline.receipt()["requests"],10*checks)

    def test_revoked_or_expired_sources_not_returned_even_with_reused_work(self):
        snap,grant,_,_=make_fixture();allowed=set(snap["sources"])
        prepared=matrix.prepare(SCOPE,QUERIES);work=ArchiveWork()
        matches,_=matrix.evaluate(snap,grant,{},allowed,NOW,prepared,work)
        sid=matches[0]["source_id"]
        revoked,_=matrix.evaluate(snap,grant,{sid:{"enabled":False,"version":1}},allowed,NOW,prepared,work)
        self.assertNotIn(sid,{x["source_id"] for x in revoked})
        expired,checks=matrix.evaluate(snap,grant,{},allowed,NOW+3*86400,prepared,work)
        self.assertEqual(expired,[]);self.assertEqual(checks,0)
        snap["sources"][sid]["text"]+="tamper"
        with self.assertRaises(ValueError):matrix.evaluate(snap,grant,{},allowed,NOW,prepared,work)

    def test_payload_dedup_preserves_best_objective_witness(self):
        snap,grant,_,_=make_fixture()
        prepared=matrix.prepare(SCOPE,QUERIES)
        found,_=matrix.evaluate(snap,grant,{},set(snap["sources"]),NOW,prepared,ArchiveWork())
        # Several independent session witnesses of the same text are not
        # independent corroboration. The strongest objective must keep its
        # exact witness even when outside the four newest copies.
        rows=[]
        for i in range(6):
            for source in found:
                hit={**source,"session_id":"session-"+str(i),"version":1,"snapshot_digest":snap["snapshot_digest"],
                     "captured_at":source["captured_at"]+i}
                if i==0:
                    hit["objectives"]=[{**x,"score":1.0} for x in source["objectives"]]
                rows.append(hit)
        result=matrix.fuse(prepared,rows,limit=128)
        self.assertEqual(result["matching_payloads"],3)
        for payload in result["payloads"]:
            self.assertLessEqual(len(payload["witnesses"]),4)
            self.assertFalse(payload["independent_corroboration_verified"])
            self.assertTrue(all(x["best_witness"]["session_id"]=="session-0" for x in payload["objectives"]))
        self.assertEqual(len(result["objectives"]),10)
        self.assertTrue(matrix.fuse(prepared,rows,limit=1)["result_truncated"])

    def test_routing_objective_bounds(self):
        with self.assertRaises(ValueError):matrix.prepare(SCOPE,[f"objective {i}" for i in range(matrix.MAX_QUERIES+1)])
        with self.assertRaises(ValueError):matrix.prepare(SCOPE,["flight","flight"])
        with self.assertRaises(ValueError):matrix.prepare(SCOPE,[""])
        prepared=matrix.prepare(SCOPE,QUERIES)
        lanes=matrix.routes(prepared)
        for lane in ("exact","rare","passage"):
            self.assertEqual(lanes[lane],sorted(set(x for p in prepared for x in p[lane])))


if __name__=="__main__":unittest.main()
