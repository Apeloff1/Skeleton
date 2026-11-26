"""Physical SQLite hundred-member fleet and hundred-objective matrix exercises."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from core.dragon_navigation_federation import NavigationFederation
from core.dragon_archive_matrix import prepare,evaluate,fuse,MatrixAccumulator,MAX_RESULT_EDGES
from core.dragon_archive_intelligence import ArchiveWork,rank_exact
from skeleton.ai.webcrawler import dragon_archive_scale as a
from test_dragon_navigation_federation import fixture,SCOPE,OTHER,NOW
from test_dragon_archive_intelligence import make_fixture


class FleetScaleTests(unittest.TestCase):
    def test_hundred_members_admitted_served_and_debited(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo=NavigationFederation(Path(temporary)/"corpus.sqlite3")
            for i in range(4):
                repo.publish(SCOPE,session_id=f"scale-source-{i}",snapshot=fixture(1500+i,128).snapshot(),
                    rights_reference="original-fixture-metadata",retention_seconds=7200,acknowledged=True,now=NOW)
            members=[]
            for i in range(100):
                row=repo.campaign(SCOPE,action="create",query="flight manual",operation=f"scale-campaign-{i:05d}",
                    budget=4096,retention_seconds=3600,acknowledged=True,now=NOW)
                members.append({"campaign_id":row["campaign_id"],"weight":1})
            fleet=repo.fleet(SCOPE,action="create",operation="hundred-scale-fleet",members=members,
                budget=409600,retention_seconds=3600,acknowledged=True,now=NOW)
            self.assertEqual(len(fleet["members"]),100)
            objectives=[{"campaign_id":m["campaign_id"],"query":"flight manual"} for m in members]
            seen=set();targets=set();spent=0;revision=1
            for i in range(100):
                result=repo.fleet(SCOPE,action="pulse",fleet_id=fleet["fleet_id"],operation=f"scale-pulse-{i:06d}",
                    objectives=objectives,budget=4,expected_revision=revision,now=NOW)
                self.assertEqual(result["state"],"complete")
                seen.add(result["campaign_id"])
                ids={x["target_id"] for x in result["targets"]}
                self.assertFalse(targets&ids);targets.update(ids)
                spent+=result["spent"];revision=result["fleet"]["revision"]
            self.assertEqual(len(seen),100)
            self.assertGreaterEqual(len(targets),100)
            self.assertEqual(result["fleet"]["remaining"],409600-spent)
            with self.assertRaises(ValueError):
                repo.fleet(OTHER,action="inspect",fleet_id=fleet["fleet_id"],now=NOW)
            replay=repo.fleet(SCOPE,action="pulse",fleet_id=fleet["fleet_id"],operation="scale-pulse-000000",
                objectives=objectives,budget=4,expected_revision=1,now=NOW)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["fleet"]["remaining"],409600-spent)


class MatrixScaleTests(unittest.TestCase):
    def test_hundred_objectives_share_authority_and_exact_features(self):
        snap,grant,_,_=make_fixture()
        queries=[f"flight manual objective{i}" for i in range(100)]
        prepared=prepare(SCOPE,queries)
        allowed=set(snap["sources"]);work=ArchiveWork()
        matches,checks=evaluate(snap,grant,{},allowed,NOW,prepared,work)
        self.assertEqual(checks,len(allowed))
        self.assertEqual(work.receipt()["requests"],checks)
        baseline=ArchiveWork()
        for query,p in zip(queries,prepared):
            terms,_=a.query_terms(SCOPE,query)
            expected=rank_exact(snap,grant,{},NOW,terms,allowed,baseline)
            observed={r["source_id"]:next(o for o in r["objectives"] if o["objective_id"]==p["id"])
                for r in matches if any(o["objective_id"]==p["id"] for o in r["objectives"])}
            self.assertEqual(set(observed),{x["source_id"] for x in expected})
            for hit in expected:
                self.assertEqual(observed[hit["source_id"]]["term_frequency"],hit["term_frequency"])
        self.assertEqual(baseline.receipt()["requests"],100*checks)

    def test_sparse_stream_matches_one_shot_and_respects_edge_budget(self):
        prepared=prepare(SCOPE,[f"flight manual topic{i}" for i in range(100)])
        rows=[]
        for i in range(100):
            rows.append({"payload":f"{i:064x}","session_id":f"session-{i}","source_id":f"{i+100:064x}",
                "version":1,"snapshot_digest":"a"*64,"valid_until":NOW+500,"captured_at":NOW+i,
                "policy_version":0,"objectives":[{"objective_id":p["id"],"score":.5,"matched_terms":1,
                    "term_frequency":1,"coverage":.5} for p in prepared]})
        oracle=fuse(prepared,rows,limit=128)
        acc=MatrixAccumulator(prepared)
        for i in range(0,len(rows),16):acc.add(rows[i:i+16])
        result=acc.result(limit=128)
        self.assertEqual(result,oracle)
        self.assertEqual(result["matching_payloads"],100)
        self.assertEqual(result["objective_edges_returned"],4000)
        self.assertLessEqual(result["objective_edges_returned"],MAX_RESULT_EDGES)
        self.assertTrue(result["objective_edge_limit_reached"])
        self.assertTrue(result["result_truncated"])
        self.assertEqual(acc.earliest_expiry,NOW+500)
        self.assertTrue(all(len(p["objectives"])==100 for p in result["payloads"]))


if __name__=="__main__":unittest.main()
