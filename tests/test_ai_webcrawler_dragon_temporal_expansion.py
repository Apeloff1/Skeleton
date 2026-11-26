"""Owner-wide temporal admission, persisted posting custody and watch authority."""
from __future__ import annotations
import copy
import hashlib
import unittest
from dataclasses import replace
from unittest.mock import patch

from skeleton.ai.webcrawler.dragon_archive_grant import create_grant
from skeleton.ai.webcrawler.dragon_index_manifest import build_manifest,load_manifest,usable_posting,same_manifest_projection
from skeleton.ai.webcrawler.dragon_temporal_selection import family_identity,select_candidates
from skeleton.ai.webcrawler.dragon_treasury import build_treasury
from skeleton.ai.webcrawler.dragon_treasury_watch import (
    create_watch,validate_watch,claim_watch,child_binding,child_matches,settle_watch,public_watch,
    same_watch_representation,
)
from test_ai_webcrawler_dragon_treasury import obs,A,B,C,NOW,DAY,BASE
from tests.test_ai_webcrawler_dragon_archive_grant import source,snapshot,CHECKPOINT,SID

SCOPE={"tenant_id":"tenant","owner_id":"owner"}


class TemporalSelectionTests(unittest.TestCase):
    def test_old_explicit_family_survives_new_capture_flood(self):
        old=[obs("old",BASE+"/important",A,NOW-3*DAY,archive=True),
             obs("new",BASE+"/important",B,NOW-2*DAY)]
        flood=[obs("recent",BASE+"/other-"+str(i),C,NOW-100-i) for i in range(40)]
        fid=family_identity(old[0])
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",8):
            result=build_treasury(old+flood,as_of=NOW,growth=1000,family=fid,mode="compare")
        self.assertTrue(result["candidate_limit_reached"])
        self.assertEqual(result["observations"],42)
        self.assertEqual(result["indexed_observations"],8)
        self.assertIsNotNone(result["comparison"])
        self.assertEqual(result["comparison"]["previous"]["source_id"],old[0].source_id)
        self.assertEqual(result["comparison"]["current"]["source_id"],old[1].source_id)
        self.assertFalse(result["evolution"]["hoarder_qualified"])

    def test_history_cutoff_excludes_future_same_content_and_alias(self):
        early=obs("early",BASE+"/instrument",A,NOW-3*DAY,archive=True)
        later=obs("later",early.url,A,NOW-100)
        changed=obs("changed",early.url,B,NOW-50)
        alias={"url":early.url,"captured_at":NOW-20,"content_hash":hashlib.sha256(C.encode()).hexdigest()}
        cutoff=NOW-2*DAY
        result=build_treasury([changed,later,early],as_of=NOW,growth=1000,
                mode="at_time",observed_before=cutoff,query="legacy",alias_blockers=[alias])
        self.assertEqual(result["observations"],1)
        self.assertEqual(result["hits"][0]["source_id"],early.source_id)
        self.assertEqual(result["hits"][0]["last_seen"],early.captured_at)
        self.assertEqual(result["hits"][0]["plane"],"historic")
        self.assertEqual(result["current_indexed"],0)
        self.assertEqual(result["revisit_plan"],[])
        self.assertIsNone(result["family_rows"][0]["refresh_url"])
        self.assertEqual(result["alias_held_families"],0)
        self.assertFalse(result["evolution"]["hoarder_qualified"])

    def test_cutoff_does_not_fallback_to_older_different_payload(self):
        early=obs("early",BASE+"/instrument",A,NOW-3*DAY,archive=True)
        held=obs("held",early.url,B,NOW-2*DAY,permitted=False)
        latest=obs("latest",early.url,C,NOW-100)
        value=build_treasury([early,held,latest],as_of=NOW,growth=800,mode="at_time",
                             observed_before=NOW-DAY)
        self.assertEqual(value["hits"],[])
        self.assertEqual(value["observations"],2)

    def test_capacity_fairness_and_order_independence(self):
        grouped={}
        for i in range(10):
            rows=[obs("s"+str(j),BASE+"/doc"+str(i),t,NOW-i*600-j*DAY)
                  for j,t in enumerate((A,B,C))]
            grouped[family_identity(rows[0])]=rows
        first=select_candidates(grouped,budget=16,family=None,observed_before=None)
        other=select_candidates(dict(reversed(list(grouped.items()))),budget=16,family=None,observed_before=None)
        self.assertEqual([(x.session_id,x.source_id) for x in first],[(x.session_id,x.source_id) for x in other])
        self.assertEqual(len(first),16)
        self.assertGreaterEqual(len({family_identity(x) for x in first}),8)

    def test_duplicate_flood_preserves_latest_transition(self):
        url=BASE+"/long-lived"
        old=obs("first",url,A,NOW-3*DAY,archive=True)
        first_change=obs("change",url,B,NOW-2*DAY)
        copies=[obs("repeat",url,B,NOW-1000+i) for i in range(50)]
        rows=[old,first_change]+copies
        fid=family_identity(old)
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",4):
            result=build_treasury(rows,as_of=NOW,growth=1000,family=fid,mode="compare")
        self.assertTrue(result["candidate_limit_reached"])
        self.assertTrue(result["comparison"]["delta"]["numeric_change"])
        self.assertEqual(result["comparison"]["previous"]["source_id"],old.source_id)
        self.assertEqual(result["comparison"]["current"]["source_id"],copies[-1].source_id)

    def test_selected_historical_pair_survives_recent_revision_flood(self):
        url=BASE+"/long-lived"
        rows=[obs("one",url,A,NOW-4*DAY,archive=True),
              obs("two",url,B,NOW-3*DAY,archive=True)]
        rows.extend(obs("later",url,C+" "+str(i),NOW-1000+i) for i in range(20))
        fid=family_identity(rows[0])
        full=build_treasury(rows,as_of=NOW,growth=1000,family=fid,mode="timeline")
        # The timeline is ordered newest first; identify original source IDs.
        by_source={v["source_id"]:v["revision_id"] for v in full["timeline"]}
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",4):
            result=build_treasury(rows,as_of=NOW,growth=1000,family=fid,mode="compare",
                                 left=by_source[rows[0].source_id],right=by_source[rows[1].source_id])
        self.assertEqual(result["comparison"]["previous"]["source_id"],rows[0].source_id)
        self.assertEqual(result["comparison"]["current"]["source_id"],rows[1].source_id)
        self.assertTrue(result["comparison"]["delta"]["numeric_change"])

    def test_unindexed_permitted_source_controls_final_expiry_fence(self):
        rows=[obs("match",BASE+"/match",A+" magnetometer",NOW-1)]
        rows.extend(obs("flood",BASE+"/noise/"+str(i),B,NOW-10-i) for i in range(20))
        expiring=replace(obs("old",BASE+"/expiring",C,NOW-3*DAY),usable_until=NOW+1)
        rows.append(expiring)
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",4):
            result=build_treasury(rows,as_of=NOW,growth=1000,query="magnetometer")
        self.assertEqual(result["earliest_source_expiry"],NOW+1)
        self.assertLess(result["indexed_observations"],len(rows))
        self.assertNotIn(expiring.source_id,{row["source_id"] for row in result["hits"]})

    def test_capped_bm25_retains_full_permitted_plane_statistics(self):
        url=BASE+"/ranked"
        rows=[obs("a",url+"/rare",A+" rare magnetometer",NOW-5000),
              obs("b",url+"/common",B+" optical magnetometer optical optical",NOW-4000)]
        rows.extend(obs("flood",url+"/"+str(i),C+" optical",NOW-i) for i in range(40))
        full=build_treasury(rows,as_of=NOW,growth=500,mode="current_only",
                           query="magnetometer optical")
        full_scores={x["source_id"]:x["score"] for x in full["hits"]}
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",8):
            limited=build_treasury(rows,as_of=NOW,growth=500,mode="current_only",
                                  query="magnetometer optical")
        self.assertEqual(limited["index_admission"],"temporal_query_rerank_v2")
        self.assertEqual(limited["query_admission"]["score_basis"],"permitted_plane_scan_bm25")
        self.assertEqual(limited["hits"][0]["source_id"],full["hits"][0]["source_id"])
        for hit in limited["hits"]:
            if hit["source_id"] in full_scores:
                self.assertEqual(hit["score"],full_scores[hit["source_id"]])
        self.assertLess(limited["indexed_observations"],limited["eligible_observations"])

    def test_capped_history_scan_never_scores_withheld_or_current_only_text(self):
        url=BASE+"/dual-plane"
        rows=[obs("historic",url,A+" relic",NOW-3*DAY,archive=True),
              obs("current",url,B+" relic",NOW-100)]
        rows.extend(obs("flood",BASE+"/other"+str(i),C+" relic",NOW-i-10) for i in range(40))
        rows.append(obs("held",BASE+"/held",A+" relic",NOW-20,permitted=False))
        with patch("skeleton.ai.webcrawler.dragon_treasury.MAX_INDEXED",4):
            history=build_treasury(rows,as_of=NOW,growth=500,mode="historic_only",query="relic")
        self.assertEqual(history["query_admission"]["eligible_representatives"],1)
        self.assertEqual(history["query_admission"]["matching_representatives"],1)
        self.assertEqual([x["source_id"] for x in history["hits"]],[rows[0].source_id])
        self.assertEqual(history["hits"][0]["plane"],"historic")

    def test_paging_bound_to_query_and_partition(self):
        rows=[obs("a",BASE+"/doc"+str(i),A,NOW-i) for i in range(32)]
        first=build_treasury(rows,as_of=NOW,growth=500,query="legacy")
        second=build_treasury(rows,as_of=NOW,growth=500,query="legacy",cursor=first["next_cursor"])
        self.assertEqual(len(first["hits"]),24)
        self.assertEqual(len(second["hits"]),8)
        self.assertFalse({x["revision_id"] for x in first["hits"]}&{x["revision_id"] for x in second["hits"]})
        with self.assertRaises(ValueError):
            build_treasury(rows,as_of=NOW,growth=500,query="different",cursor=first["next_cursor"])


class PostingManifestTests(unittest.TestCase):
    def test_rebuild_excludes_revoked_members_without_touching_original_grant(self):
        first=source(fetched_at=NOW-20)
        other=source(source_id="c"*64,fetched_at=NOW-10)
        snap=snapshot(first)
        snap["sources"][other["source_id"]]=other
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=2)
        original=copy.deepcopy(grant)
        prior=build_manifest(snap,grant,now=NOW)
        repaired=build_manifest(snap,grant,now=NOW+1,policies={SID:{"enabled":False,"version":1}})
        loaded=load_manifest(repaired,grant,snapshot_digest=CHECKPOINT,now=NOW+1)
        self.assertEqual(set(loaded),{other["source_id"]})
        self.assertEqual(grant,original)
        self.assertEqual(repaired["grant_digest"],prior["grant_digest"])
        self.assertFalse(same_manifest_projection(prior,repaired,grant,now=NOW+1))
        self.assertTrue(same_manifest_projection(repaired,repaired,grant,now=NOW+1))

    def test_all_members_withdrawn_produces_valid_empty_derivative(self):
        snap=snapshot(source(fetched_at=NOW-20))
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=1)
        empty=build_manifest(snap,grant,now=NOW+1,policies={SID:{"enabled":True,"version":1}})
        self.assertEqual(empty["source_count"],0)
        self.assertEqual(load_manifest(empty,grant,snapshot_digest=CHECKPOINT,now=NOW+1),{})
        self.assertTrue(same_manifest_projection(empty,empty,grant,now=NOW+1))
        self.assertFalse(same_manifest_projection({"source_count":0},empty,grant,now=NOW+1))

    def test_scheduled_audit_independently_checks_projection_and_corruption(self):
        snap=snapshot(source(fetched_at=NOW-20))
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=1)
        expected=build_manifest(snap,grant,now=NOW+100,policies={})
        initial=build_manifest(snap,grant,now=NOW,policies={})
        self.assertTrue(same_manifest_projection(initial,expected,grant,now=NOW+100))
        self.assertFalse(same_manifest_projection({**initial,"segment":"AAAA"},expected,grant,now=NOW+100))
        self.assertFalse(same_manifest_projection({**initial,"raw_sha256":"f"*64},expected,grant,now=NOW+100))

    def test_segment_compression_admission_is_bounded(self):
        snap=snapshot(source(fetched_at=NOW-20))
        for i in range(1,12):
            sid=format(i,"064x")
            snap["sources"][sid]=source(source_id=sid,fetched_at=NOW-i,
                text=" ".join(hashlib.sha256(f"{i}-{j}".encode()).hexdigest() for j in range(200)))
            row=snap["sources"][sid]
            row["preserved_text_hash"]=hashlib.sha256(row["text"].encode()).hexdigest()
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=1)
        with patch("skeleton.ai.webcrawler.dragon_index_manifest.MAX_COMPRESSED",4000):
            result=build_manifest(snap,grant,now=NOW,policies={})
            entries=load_manifest(result,grant,snapshot_digest=CHECKPOINT,now=NOW)
            self.assertLess(len(entries),len(grant["members"]))
            self.assertEqual(len(entries),result["source_count"])


    def test_cached_projection_equals_reparse_and_policy_change_fails_closed(self):
        src=source(fetched_at=NOW-100)
        snap=snapshot(src)
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=1)
        manifest=build_manifest(snap,grant,now=NOW)
        entries=load_manifest(manifest,grant,snapshot_digest=CHECKPOINT,now=NOW+1)
        posting=usable_posting(entries,src,{"enabled":True,"version":0})
        self.assertIsNotNone(posting)
        self.assertIsNone(usable_posting(entries,src,{"enabled":True,"version":1}))
        self.assertIsNone(usable_posting(entries,src,{"enabled":False,"version":0}))
        self.assertEqual(load_manifest(manifest,grant,snapshot_digest=CHECKPOINT,now=NOW+DAY),{})
        row=obs("a",BASE+"/doc",src["text"],NOW-100,archive=True)
        raw=build_treasury([row],as_of=NOW+1,growth=500,mode="historic_only")
        cached=build_treasury([row],as_of=NOW+1,growth=500,mode="historic_only",
            materialized={(row.session_id,row.source_id):posting})
        self.assertEqual(raw["hits"],cached["hits"])
        self.assertEqual(raw["partition_digest"],cached["partition_digest"])
        self.assertEqual(cached["materialized_payload_hits"],1)

    def test_corrupt_or_expired_segment_never_returns_postings(self):
        snap=snapshot(source(fetched_at=NOW-10))
        grant=create_grant(snapshot=snap,policies={},now=NOW,days=1)
        manifest=build_manifest(snap,grant,now=NOW)
        for mutation in ({"raw_sha256":"f"*64},{"segment":"AAAA"},{"raw_bytes":2},
                         {"source_count":65}):
            with self.assertRaises(ValueError):
                load_manifest({**manifest,**mutation},grant,snapshot_digest=CHECKPOINT,now=NOW+1)


class WatchTests(unittest.TestCase):
    def new_watch(self,**kwargs):
        inputs={"operation":"d"*64,"parent_id":"parent","scope":SCOPE,"principal_email":"a@example.org",
                "snapshot_digest":CHECKPOINT,"source":{"source_id":SID,"fetched_url":BASE+"/page",
                "content_hash":"e"*64,"fetched_at":NOW-DAY},"policy_version":0,"now":NOW,
                "days":7,"cycles":2,"minimum_interval":21600,"retention_days":30}
        return create_watch(**{**inputs,**kwargs})

    def test_claim_recovery_same_cycle_and_no_budget_refund(self):
        watch=self.new_watch()
        due=watch["next_due"]
        first=claim_watch(watch,now=due,token="first")
        self.assertEqual(first["cycles_started"],1)
        self.assertEqual(first["active_cycle"],1)
        with self.assertRaises(ValueError):
            claim_watch(first,now=due+1,token="second")
        second=claim_watch(first,now=due+181,token="second")
        self.assertEqual(second["cycles_started"],1)
        self.assertEqual(child_binding(first),child_binding(second))
        self.assertNotEqual(first["claim_token"],second["claim_token"])
        stopped={**second,"enabled":False,"state":"stopped","stop_reason":"operator_revoked"}
        self.assertFalse(child_matches(child_binding(second),stopped,now=due+182))

    def test_success_settles_only_exact_observed_sample(self):
        watch=self.new_watch()
        due=watch["next_due"]
        active=claim_watch(watch,now=due,token="first")
        captured={"at":due+2,"digest":"c"*64}
        settled=settle_watch(active,now=due+3,child_id="child",sample=captured,completed=True)
        self.assertEqual(settled["cycles_completed"],1)
        self.assertEqual(settled["samples"][-1],captured)
        self.assertIsNone(settled["active_cycle"])
        self.assertGreaterEqual(settled["next_due"],due+3+watch["minimum_interval"])
        self.assertFalse(child_matches(child_binding(active),settled,now=due+3))
        public=public_watch(settled,now=due+3)
        self.assertNotIn("principal_email",public)
        self.assertNotIn("samples",public)

    def test_failed_attempt_never_earns_change_sample(self):
        watch=self.new_watch()
        due=watch["next_due"]
        active=claim_watch(watch,now=due,token="first")
        failed=settle_watch(active,now=due+3,child_id="child",sample=None,completed=False)
        self.assertEqual(failed["samples"],watch["samples"])
        self.assertGreaterEqual(failed["next_due"],due+DAY)
        self.assertEqual(failed["cycles_completed"],1)

    def test_representation_boundary_holds_language_media_vary_and_missing_receipts(self):
        parent=source(fetched_url=BASE+"/page",content_type="text/plain")
        parent["provenance"]["http_freshness"].update(languages=["en"],vary_dimensions=["accept-language"])
        self.assertTrue(same_watch_representation(parent,copy.deepcopy(parent)))
        tuple_form=copy.deepcopy(parent)
        tuple_form["provenance"]["http_freshness"].update(languages=("en",),vary_dimensions=("accept-language",))
        self.assertTrue(same_watch_representation(parent,tuple_form))
        for field,value in (("languages",["no"]),("vary_dimensions",[]),("private",True),
                            ("no_store",True),("sensitive_vary",True)):
            other=copy.deepcopy(parent)
            other["provenance"]["http_freshness"][field]=value
            self.assertFalse(same_watch_representation(parent,other))
        self.assertFalse(same_watch_representation(parent,{**parent,"content_type":"text/html"}))
        self.assertFalse(same_watch_representation(parent,{**parent,"fetched_url":BASE+"/redirect"}))
        other=copy.deepcopy(parent)
        del other["provenance"]["http_freshness"]["languages"]
        self.assertFalse(same_watch_representation(parent,other))

    def test_expired_claim_and_nonfinite_clock_cannot_settle(self):
        watch=self.new_watch()
        due=watch["next_due"]
        active=claim_watch(watch,now=due,token="first")
        with self.assertRaises(ValueError):
            claim_watch(watch,now=float("nan"),token="first")
        with self.assertRaises(ValueError):
            settle_watch(active,now=active["claim_until"],child_id="child",sample=None,completed=False)
        self.assertFalse(child_matches(child_binding(active),active,now=float("nan")))
        self.assertFalse(child_matches(child_binding(active),active,now=due,margin=-1))
        self.assertFalse(child_matches(child_binding(active),{**active,"state":"blocked"},now=due))
        resumed=claim_watch(active,now=active["claim_until"],token="second")
        self.assertEqual(child_binding(active),child_binding(resumed))
        result=settle_watch(resumed,now=resumed["claim_until"]-1,child_id="child",sample=None,completed=False)
        self.assertEqual(result["cycles_completed"],1)

    def test_invalid_watch_scope_and_deadline_denied(self):
        for url in ("https://example.org/a?token=x","https://user@example.org/a","file:///tmp/a"):
            with self.assertRaises(ValueError):
                self.new_watch(source={"source_id":SID,"fetched_url":url,"content_hash":"e"*64,"fetched_at":NOW-DAY})
        w=self.new_watch()
        with self.assertRaises(ValueError):
            validate_watch({**w,"cycles_started":7})
        with self.assertRaises(ValueError):
            claim_watch(w,now=w["expires_at"],token="late")


if __name__=="__main__":
    unittest.main()
