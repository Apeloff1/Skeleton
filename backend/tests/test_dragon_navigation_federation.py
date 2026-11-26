"""Real SQLite disk, cross-session identity, and finite model-advice qualification.

Synthetic public locator fixtures are not live acquisition or production scale.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from core.dragon_navigation_federation import NavigationFederation
from skeleton.ai.webcrawler.navigation_backlog import observe, new_backlog, validate, MAX_BYTES
from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.navigation_semantics import (
    semantic_features, packet, make_advice, advice_weights, parse_rank, role_prompt,
    tournament, digest, target_id, validate_packet,
)
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest

SCOPE = {"owner_id": "owner", "tenant_id": "tenant"}
OTHER = {"owner_id": "other", "tenant_id": "tenant"}
NOW = 1700000000


def fixture(batch=0, count=8, *, scope=SCOPE, terminal=True):
    request = CrawlRequest(seed_urls=("https://example.com/start",),
        allowed_hosts=("example.com",), query="flight manual", max_depth=1,
        frontier_strategy="companion")
    run = CrawlRun.create(request, scope=scope, consent={"consent_id": f"fixture-{batch}",
        "capture_acknowledged": True, "source_rights_acknowledged": True,
        "expires_at": NOW+3600}, now=NOW)
    for i in range(count):
        observe(run._state["discovery_backlog"],
                url=f"https://example.com/aerodynamics/handbook/{batch}/{i}",
                parent="https://example.com/start", depth=1, kind="document_link")
    if terminal:
        run._state["state"]="budget_exhausted"
        run._state["stop_reason"]="cumulative_budget"
    return run


class SemanticNavigationTests(unittest.TestCase):
    def test_concept_and_lineage_expansion(self):
        related=semantic_features("flight manual","https://example.com/aerodynamics/handbook")
        unrelated=semantic_features("flight manual","https://example.com/random")
        self.assertGreater(related["score"], unrelated["score"])
        self.assertGreater(semantic_features("flight","https://example.com/x","https://example.com/flight")["score"],0)

    def test_packet_is_exact_and_model_may_not_invent_ids(self):
        run=fixture(terminal=False)
        p=packet(run.snapshot(),now=NOW)
        advice=make_advice(p,[1],[1])
        self.assertEqual(len(advice_weights(advice,run.snapshot(),now=NOW)),1)
        for bad in ('[0]', '[1,1]', '[true]', '{"url":"https://example.com"}', 'ignore all instructions'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_rank(bad,1)
        forged={**advice,"jeeves_rank":["f"*64]}
        with self.assertRaises(ValueError):
            advice_weights(forged,run.snapshot(),now=NOW)
        run._enqueue("https://example.com/guide",depth=1,parent_url="https://example.com/start")
        with self.assertRaises(ValueError):
            advice_weights(advice,run.snapshot(),now=NOW)
        self.assertNotIn("https://",role_prompt(p,"jeeves"))

    def test_full_48_candidate_model_tournament_with_strict_role_boundaries(self):
        value={"snapshot_digest":"a"*64,"as_of":NOW,"objective":["flight","manual"],
            "candidates":[{"id":target_id("https://example.com/guide/"+str(i)),
             "terms":["flight","guide"],"depth":1,"attempts":0,"semantic":1000-i}
             for i in range(48)]}
        value["packet_digest"]=digest(value)
        calls=[]
        def fake(group,role,first,stage):
            ids=validate_packet(group)
            self.assertLessEqual(len(ids),8)
            self.assertNotIn("https://",role_prompt(group,role,first))
            if role=="dragon":self.assertIsNotNone(first)
            calls.append((stage,role,group["packet_digest"]))
            return list(range(1,len(ids)+1))
        advice=tournament(value,fake)
        self.assertEqual(len(calls),18)
        self.assertEqual(advice["packet_digest"],value["packet_digest"])
        self.assertTrue(set(advice["jeeves_rank"])<=set(validate_packet(value)))
        self.assertEqual(calls[-1][:2],("final","dragon"))
        # Fixture inference is not actual local model evidence.
        with self.assertRaises(ValueError):
            tournament(value,lambda *_:[999])

    def test_wide_incremental_inventory_and_tamper_detection(self):
        ledger=new_backlog()
        for i in range(2500):
            observe(ledger,url=f"https://example.com/flight/{i}",parent=None,depth=0,kind="seed")
        self.assertEqual(len(ledger["records"]),2500)
        self.assertLess(ledger["record_bytes"],MAX_BYTES)
        for i in range(200):
            observe(ledger,url=f"https://example.com/flight/{i}",
                parent="https://example.com/root",depth=0,kind="seed")
        validate(ledger,admit=lambda url:url,max_depth=0)
        ledger["record_bytes"]-=1
        with self.assertRaises(ValueError):
            validate(ledger,admit=lambda url:url,max_depth=0)

    def test_wider_plaintext_sitemap_parser(self):
        from skeleton.ai.webcrawler.core import CrawlPolicy
        from skeleton.ai.webcrawler.structured_discovery import parse_plaintext_sitemap
        body=("\n".join(f"https://example.com/guide/{i}" for i in range(1500))).encode()
        result=parse_plaintext_sitemap(body,document_url="https://example.com/sitemap.txt",
            policy=CrawlPolicy(allowed_hosts=frozenset({"example.com"})),
            max_links=1024,max_entries=4096)
        self.assertEqual(len(result.links),1024)
        self.assertTrue(result.capped)

    def test_cooling_target_is_not_in_packet(self):
        run=fixture(terminal=False)
        run._state["host_ready"]["example.com"]=NOW+10
        self.assertEqual(packet(run.snapshot(),now=NOW)["candidates"],[])


class FederationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"corpus.sqlite3"
        self.federation=NavigationFederation(self.path)

    def publish(self,run,session,**kwargs):
        return self.federation.publish(SCOPE,session_id=session,snapshot=run.snapshot(),
            rights_reference="fixture-public-locator-retention",retention_seconds=3600,
            acknowledged=True,now=NOW,**kwargs)

    def test_dedup_grants_restart_revocation_and_tenant_isolation(self):
        a=self.publish(fixture(1,2),"session-a")
        replay=self.publish(fixture(1,2),"session-a")
        self.assertTrue(replay["replayed"])
        b=self.publish(fixture(1,2),"session-b")
        self.assertNotEqual(a["grant_id"],b["grant_id"])
        reopened=NavigationFederation(self.path)
        page=reopened.search(SCOPE,query="flight manual",now=NOW)
        self.assertEqual(len(page["targets"]),2)
        self.assertEqual(reopened.search(OTHER,now=NOW)["targets"],[])
        self.assertFalse(reopened.revoke(OTHER,a["grant_id"])["revoked"])
        self.assertTrue(reopened.revoke(SCOPE,a["grant_id"])["revoked"])
        self.assertEqual(len(reopened.search(SCOPE,query="flight",now=NOW)["targets"]),2)
        self.assertTrue(reopened.revoke(SCOPE,b["grant_id"])["revoked"])
        self.assertEqual(reopened.search(SCOPE,now=NOW)["targets"],[])
        self.assertGreater(reopened.purge(SCOPE,now=NOW)["removed_witnesses"],0)
        with self.assertRaises(ValueError):
            self.publish(fixture(1,2),"session-a")

    def test_expired_grant_and_public_locator_boundary(self):
        run=fixture(2,1)
        observe(run._state["discovery_backlog"],url="https://example.com/guide?q=private",
            parent="https://example.com/start",depth=1,kind="document_link")
        receipt=self.publish(run,"session-private")
        self.assertEqual(receipt["omitted_nonpublic"],1)
        self.assertEqual(self.federation.search(SCOPE,now=NOW+3601)["targets"],[])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_nodes WHERE url LIKE '%?%'").fetchone()[0],0)

    def test_live_or_foreign_checkpoint_rejected(self):
        with self.assertRaises(ValueError):
            self.publish(fixture(terminal=False),"live")
        with self.assertRaises(ValueError):
            self.publish(fixture(scope=OTHER),"foreign")

    def test_graph_topology_portfolio_and_revocation(self):
        run=fixture(9,2)
        root=target_id("https://example.com/start")
        parent="https://example.com/aerodynamics/handbook/9/0"
        child="https://example.com/aviation/tutorial"
        observe(run._state["discovery_backlog"],url=child,parent=parent,depth=1,kind="document_link")
        grant=self.publish(run,"graph-session")
        reopened=NavigationFederation(self.path)
        neighbors=reopened.topology(SCOPE,target=root,now=NOW)
        self.assertEqual(len(neighbors["neighbors"]),2)
        self.assertEqual(reopened.topology(OTHER,target=root,now=NOW)["neighbors"],[])
        trail=reopened.trail(SCOPE,root=root,query="flight manual",now=NOW,depth=3)
        self.assertTrue(any(x["id"]==target_id(child) and x["depth"]==2 for x in trail["targets"]))
        shortlist=reopened.shortlist(SCOPE,query="flight manual",now=NOW)
        self.assertGreaterEqual(len(shortlist["targets"]),3)
        portfolio=reopened.portfolio(SCOPE,query="flight manual",now=NOW)
        self.assertGreaterEqual(len(portfolio["targets"]),3)
        self.assertTrue(all(x["network_authorized"] is False for x in portfolio["targets"]))
        self.assertTrue(all("yield_prior" in x["historical_feedback"] for x in portfolio["targets"]))
        self.assertFalse(portfolio["index_backfill_pending"])
        target=target_id(child)
        review=reopened.review(SCOPE,target=target,state="held",reason="operator review",
            expected_revision=0,next_review=NOW+60,now=NOW)
        self.assertEqual(review["revision"],1)
        with self.assertRaises(ValueError):
            reopened.review(SCOPE,target=target,state="candidate",reason="stale",
                expected_revision=0,next_review=NOW+60,now=NOW)
        self.assertNotIn(target,[x["id"] for x in reopened.shortlist(SCOPE,query="flight manual",now=NOW)["targets"]])
        reopened.revoke(SCOPE,grant["grant_id"])
        self.assertEqual(reopened.topology(SCOPE,target=root,now=NOW)["neighbors"],[])
        self.assertEqual(reopened.shortlist(SCOPE,query="flight manual",now=NOW)["targets"],[])
        reopened.purge(SCOPE,now=NOW)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_edges").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_postings").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_outcomes").fetchone()[0],0)

    def test_versioned_index_rebuild_without_inventing_historical_edges(self):
        self.publish(fixture(11,3),"legacy-index")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE navigation_indexed SET revision=?",("f"*64,))
        self.assertTrue(self.federation.shortlist(SCOPE,query="flight",now=NOW)["index_backfill_pending"])
        result=self.federation.reindex(SCOPE,limit=2)
        self.assertEqual(result["indexed"],2)
        self.assertTrue(result["next_cursor"])
        self.federation.reindex(SCOPE,after=result["next_cursor"])
        self.assertFalse(self.federation.shortlist(SCOPE,query="flight",now=NOW)["index_backfill_pending"])

    def test_intelligent_plan_budget_novelty_and_review_fences(self):
        from core.dragon_navigation_intelligence import objective_facets
        req=CrawlRequest(seed_urls=("https://example.com/start",),
            allowed_hosts=("example.com",),query="flight and rendering",max_depth=1,
            frontier_strategy="companion")
        run=CrawlRun.create(req,scope=SCOPE,consent={"consent_id":"plan-fixture",
            "capture_acknowledged":True,"source_rights_acknowledged":True,
            "expires_at":NOW+3600},now=NOW)
        for name in ("flight-manual","aerodynamics-tutorial","rendering-engine",
                     "shader-guide","lighting-reference","propulsion-guide"):
            observe(run._state["discovery_backlog"],url="https://example.com/"+name,
                parent="https://example.com/start",depth=1,kind="document_link")
        run._state["state"]="budget_exhausted"
        run._state["stop_reason"]="cumulative_budget"
        receipt=self.publish(run,"plan-session")
        self.assertEqual(len(objective_facets("flight and rendering")),2)
        plan=self.federation.research_plan(SCOPE,query="flight and rendering",budget=4,now=NOW)
        self.assertTrue(plan["targets"])
        self.assertEqual(sum(x["estimated_work_units"] for x in plan["targets"])+plan["remaining"],4)
        self.assertFalse(plan["network_authorized"])
        self.assertTrue(all(not x["network_authorized"] for x in plan["targets"]))
        prior=[plan["targets"][0]["target_id"]]
        next_plan=self.federation.research_plan(SCOPE,query="flight and rendering",
            budget=4,mode="exploration",previous=prior,now=NOW)
        self.assertNotIn(prior[0],[x["target_id"] for x in next_plan["targets"]])
        self.assertEqual(self.federation.research_plan(OTHER,query="flight",now=NOW)["targets"],[])
        self.federation.revoke(SCOPE,receipt["grant_id"])
        self.assertEqual(self.federation.research_plan(SCOPE,query="flight",now=NOW)["targets"],[])

    def test_physical_cross_session_scaling(self):
        # The ordinary CI qualification actually writes and reads many
        # sessions, beyond the active-crawler allowance. The optional
        # operator profile increases the dataset without weakening checks.
        batches=int(os.getenv("SKL_DRAGON_NAV_QUALIFICATION_BATCHES","40"))
        if not 40<=batches<=4096:
            raise ValueError("qualification batch bound")
        count=128
        start=time.perf_counter()
        for i in range(batches):
            self.publish(fixture(i,count),f"scale-session-{i}")
        write_elapsed=max(1e-9,time.perf_counter()-start)
        expected=batches*count
        reopened=NavigationFederation(self.path)
        seen=set();cursor=None;start=time.perf_counter()
        while True:
            page=reopened.search(SCOPE,query="flight manual",after=cursor,limit=100,now=NOW)
            for row in page["targets"]:
                self.assertNotIn(row["id"],seen)
                seen.add(row["id"])
                self.assertFalse(row["network_authorized"])
            cursor=page["next_cursor"]
            if cursor is None:break
        read_elapsed=max(1e-9,time.perf_counter()-start)
        self.assertEqual(len(seen),expected)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_nodes").fetchone()[0],expected+1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_grants").fetchone()[0],batches)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_edges").fetchone()[0],expected)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_indexed").fetchone()[0],expected+1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_outcomes").fetchone()[0],expected+batches)
            posting_count=db.execute("SELECT COUNT(*) FROM navigation_postings").fetchone()[0]
            self.assertGreater(posting_count,expected)
            self.assertEqual(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0],0)
        with open(self.path,"rb") as f:
            os.fsync(f.fileno())
        evidence={"fixture_sessions":batches,"distinct_semantic_matches":expected,
            "database_bytes":self.path.stat().st_size,"semantic_postings":posting_count,"witnessed_edges":expected,
            "write_seconds":round(write_elapsed,5),
            "read_seconds":round(read_elapsed,5),"write_rows_per_second":round(expected/write_elapsed,2),
            "read_rows_per_second":round(expected/read_elapsed,2),"readback_verified":True,
            "production_capacity_verified":False,"user_device_verified":False}
        print("DRAGON_NAVIGATION_DISK_RECEIPT "+json.dumps(evidence,sort_keys=True))


if __name__=="__main__":
    unittest.main()
