"""Cold custody contract and history-only bounded retrieval regressions."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.webcrawler.dragon_treasury_vault import (
    MAX_VAULT_SESSIONS, selected_ids, make_marker, validate_marker,
    reserve_filter, release_active_filter, public_marker,
)
from skeleton.ai.webcrawler.dragon_treasury import build_treasury
from tests.test_ai_webcrawler_dragon_treasury import obs,A,B,NOW,DAY,BASE

SCOPE={"tenant_id":"tenant","owner_id":"owner"}


class VaultContractTests(unittest.TestCase):
    def marker(self):
        return make_marker(operation="a"*64,request_digest="b"*64,
                           snapshot_digest="c"*64,now=NOW)

    def test_finite_distinct_window(self):
        self.assertEqual(selected_ids(["b","a"]),("a","b"))
        self.assertEqual(len(selected_ids([str(i) for i in range(32)])),32)
        for values in ([],["a","a"],["a/b"],["../x"],["x"*129],
                       [str(i) for i in range(33)],["a",None],"a"):
            with self.subTest(values=values), self.assertRaises(ValueError):
                selected_ids(values)

    def test_irrevocable_marker_never_claims_new_authority(self):
        marker=self.marker()
        self.assertFalse(public_marker(marker)["execution_authorized"])
        self.assertFalse(public_marker(marker)["historical_grant_extended"])
        self.assertNotIn("operation",public_marker(marker))
        self.assertNotIn("request_digest",public_marker(marker))
        for patch in ({"active_slot_released":True},{"retry_at":NOW-1},
                      {"accepted_at":float("nan")},{"state":"active"},
                      {"snapshot_digest":"invalid"},{"execution_authorized":True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_marker({**marker,**patch})
        self.assertTrue(public_marker({**marker,"state":"vaulted",
                                       "active_slot_released":True})["active_slot_released"])

    def test_quota_filter_reserves_before_release(self):
        query=reserve_filter(SCOPE,"d"*64,"session")
        self.assertEqual(query["$or"],[{"vault_ids":"session"},
            {"session_ids":"session",f"vault_ids.{MAX_VAULT_SESSIONS-1}":{"$exists":False}}])
        release=release_active_filter(SCOPE,"d"*64,"session")
        self.assertEqual(release["vault_ids"],"session")
        self.assertEqual(release["owner_id"],SCOPE["owner_id"])

    def test_window_never_promotes_history_or_offers_revisit(self):
        rows=[replace(obs("a",BASE+"/doc",A,NOW-2*DAY,archive=True),refresh_allowed=False),
              replace(obs("b",BASE+"/doc",B,NOW-DAY,archive=True),refresh_allowed=False)]
        result=build_treasury(rows,as_of=NOW,growth=0,mode="historic_only",
            catalogue_scope=("a","b"),candidate_limit_reached=True)
        self.assertEqual(result["historic_indexed"],2)
        self.assertEqual(result["current_indexed"],0)
        self.assertEqual(result["revisit_plan"],[])
        self.assertFalse(result["evolution"]["hoarder_qualified"])
        self.assertEqual(result["evolution"]["expedition_growth"],0)
        self.assertTrue(all(hit["archive_only"] and hit["plane"]=="historic" for hit in result["hits"]))
        for changes in ({"mode":"current_only"},{"candidate_limit_reached":False},
                        {"growth":800},{"catalogue_scope":("a",)}):
            kwargs={"mode":"historic_only","candidate_limit_reached":True,"growth":0,
                    "catalogue_scope":("a","b"),**changes}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_treasury(rows,as_of=NOW,**kwargs)
        for bad in (replace(rows[0],archive_only=False),replace(rows[0],refresh_allowed=True)):
            with self.assertRaises(ValueError):
                build_treasury([bad,rows[1]],as_of=NOW,growth=0,mode="historic_only",
                    catalogue_scope=("a","b"),candidate_limit_reached=True)

    def test_cursor_binds_selected_scope_even_if_no_text_differs(self):
        rows=[replace(obs("a",BASE+f"/doc/{i}",A,NOW-i,archive=True),refresh_allowed=False)
              for i in range(50)]
        first=build_treasury(rows,as_of=NOW,growth=0,mode="historic_only",
                             catalogue_scope=("a",),candidate_limit_reached=True)
        self.assertIsNotNone(first["next_cursor"])
        second=build_treasury(rows,as_of=NOW,growth=0,mode="historic_only",
            catalogue_scope=("a",),candidate_limit_reached=True,cursor=first["next_cursor"])
        self.assertEqual(second["page_offset"],24)
        with self.assertRaisesRegex(ValueError,"cursor"):
            build_treasury(rows,as_of=NOW,growth=0,mode="historic_only",
                catalogue_scope=("a","b"),candidate_limit_reached=True,cursor=first["next_cursor"])


class VaultQuotaTests(unittest.TestCase):
    def test_conservative_classification_and_exact_array_fence(self):
        from skeleton.ai.webcrawler.dragon_vault_quota import classify_quota,quota_fence
        marker=make_marker(operation="a"*64,request_digest="b"*64,snapshot_digest="c"*64,now=NOW)
        def row(sid,status,**rest):
            return {"_id":sid,**SCOPE,"version":1,"status":status,**rest}
        doc={"_id":"d"*64,"session_ids":["active","pending","both","missing","deleted","bad"],
             "vault_ids":["both","vault","deleted"]}
        witness={"snapshot_digest":"c"*64}
        rows=[row("active","queued"),row("pending","completed",treasury_vault=marker,checkpoint_identity=witness),
              row("both","completed",treasury_vault={**marker,"state":"vaulted"},checkpoint_identity=witness),
              row("vault","completed",treasury_vault={**marker,"state":"vaulted","active_slot_released":True},checkpoint_identity=witness),
              row("deleted","deleted",deletion={"operation":"d"*64,"request_digest":"e"*64}),
              row("bad","deleted",deletion={"operation":"wrong","request_digest":"e"*64})]
        counts,releasable=classify_quota(doc,rows,SCOPE)
        self.assertEqual(releasable,["deleted"])
        self.assertEqual((counts["active"],counts["vaulted"],counts["in_transit"],counts["missing"],
                          counts["tombstoned"],counts["integrity_held"]),(1,1,2,1,1,1))
        self.assertEqual(counts["dual_reserved"],2)
        self.assertEqual(counts["distinct_reserved"],7)
        self.assertEqual(quota_fence(doc,SCOPE)["session_ids"],doc["session_ids"])
        self.assertEqual(quota_fence({"_id":"a"},SCOPE)["vault_ids"],{"$exists":False})

    def test_rejects_malformed_or_foreign_metadata(self):
        from skeleton.ai.webcrawler.dragon_vault_quota import classify_quota
        for doc in ({"session_ids":["a","a"]},{"vault_ids":[str(i) for i in range(MAX_VAULT_SESSIONS+1)]},
                    {"session_ids":["../bad"]},{"vault_ids":None}):
            with self.assertRaises(ValueError):
                classify_quota(doc,[],SCOPE)
        for another in ({"_id":"a",**SCOPE,"owner_id":"foreign","version":1,"status":"deleted"},
                        {"_id":"b",**SCOPE,"version":1,"status":"deleted"}):
            with self.assertRaises(ValueError):
                classify_quota({"session_ids":["a"]},[another],SCOPE)

    def test_partial_tombstone_is_never_reclaimed(self):
        from skeleton.ai.webcrawler.dragon_vault_quota import classify_quota
        row={"_id":"a",**SCOPE,"version":1,"status":"deleted",
             "deletion":{"operation":"a"*64,"request_digest":"b"*64},"checkpoint_identity":{}}
        counts,removed=classify_quota({"session_ids":["a"]},[row],SCOPE)
        self.assertEqual(removed,[])
        self.assertEqual(counts["integrity_held"],1)


class VaultDiscoveryTests(unittest.TestCase):
    def test_exact_retained_payload_dedup_and_coverage(self):
        import hashlib
        from skeleton.ai.webcrawler.dragon_vault_discovery import query_terms,summarize_sources
        def source(text):
            return {"text":text,"preserved_text_hash":hashlib.sha256(text.encode()).hexdigest()}
        rows=[source("optical magnetometer"),source("optical magnetometer"),source("magnetometer"),source("unrelated")]
        summary=summarize_sources(rows,query_terms("optical magnetometer"))
        self.assertEqual(summary["matched_sources"],3)
        self.assertEqual(summary["distinct_matching_payloads"],2)
        self.assertEqual(summary["matched_terms"],2)
        self.assertEqual(summary["best_source_terms"],2)
        with self.assertRaises(ValueError):
            summarize_sources([{**rows[0],"text":"tampered"}],query_terms("optical"))

    def test_catalogue_cursor_changes_on_query_version_and_grant_expiry(self):
        from skeleton.ai.webcrawler.dragon_vault_discovery import catalogue_signature,digest_scope,page_offset,query_terms
        rows=[{"_id":f"s{i:02}","version":1,"archive_grant":{"issued_at":NOW-100,"expires_at":NOW+1}}
              for i in reversed(range(12))]
        sig=catalogue_signature(rows,now=NOW)
        bound=digest_scope(SCOPE,sig,query_terms("optical"))
        cursor=bound+":8"
        self.assertEqual(page_offset(cursor,bound,12),8)
        for other in (digest_scope(SCOPE,sig,query_terms("other")),
                      digest_scope(SCOPE,catalogue_signature(rows,now=NOW+2),query_terms("optical")),
                      digest_scope({**SCOPE,"owner_id":"other"},sig,query_terms("optical"))):
            with self.assertRaises(ValueError):
                page_offset(cursor,other,12)
        for bad in (bound+":1",bound+":0",bound+":08",bound+":16"):
            with self.assertRaises(ValueError):
                page_offset(bad,bound,12)
        rows[0]["version"]=2
        self.assertNotEqual(digest_scope(SCOPE,catalogue_signature(rows,now=NOW),query_terms("optical")),bound)

    def test_invalid_query_or_oversized_catalogue_rejected(self):
        from skeleton.ai.webcrawler.dragon_vault_discovery import query_terms,catalogue_signature
        for query in ("","   ","x"*257,"!!!"):
            with self.assertRaises(ValueError):
                query_terms(query)
        with self.assertRaises(ValueError):
            catalogue_signature([{"_id":str(i),"version":1} for i in range(MAX_VAULT_SESSIONS+1)],now=NOW)
        for rows in ([None],[{"_id":"a","version":1,"archive_grant":"broken"}]):
            with self.assertRaises(ValueError):
                catalogue_signature(rows,now=NOW)

    def test_all_128_positions_are_covered_in_sixteen_disjoint_batches(self):
        from skeleton.ai.webcrawler.dragon_vault_discovery import PAGE,catalogue_signature,digest_scope,page_offset,query_terms
        rows=[{"_id":f"chamber-{i:03}","version":1} for i in reversed(range(128))]
        sig=catalogue_signature(rows,now=NOW)
        bound=digest_scope(SCOPE,sig,query_terms("optical"))
        cursor=None
        visited=[]
        for batch in range(16):
            offset=page_offset(cursor,bound,len(rows))
            self.assertEqual(offset,batch*PAGE)
            visited.extend(row["_id"] for row in rows[offset:offset+PAGE])
            cursor=bound+":"+str(offset+PAGE) if offset+PAGE<len(rows) else None
        self.assertIsNone(cursor)
        self.assertEqual(len(set(visited)),128)
        self.assertEqual(visited,[row["_id"] for row in rows])


class FiniteCareContractTests(unittest.TestCase):
    def test_finite_budget_expiry_and_witness(self):
        from skeleton.ai.webcrawler.dragon_vault_care import issue_care,consume_care,public_care
        grant=issue_care(operation="a"*64,request_digest="b"*64,snapshot_digest="c"*64,
                         principal_email="owner@example.test",now=NOW,days=7,budget=2)
        first=consume_care(grant,now=NOW+1,version=7,witness="c"*64,side="primary")
        second=consume_care(first,now=NOW+2,version=8,witness="c"*64,side="replica")
        self.assertEqual(second["used"],2)
        self.assertNotIn("principal_email",public_care(first,now=NOW+1,version=8,witness="c"*64))
        self.assertFalse(public_care(second,now=NOW+2,version=9,witness="c"*64)["active"])
        for item,stamp,witness in ((second,NOW+3,"c"*64),(grant,NOW+7*DAY,"c"*64),
                                  (grant,NOW+1,"d"*64),({**grant,"enabled":False},NOW+1,"c"*64)):
            with self.assertRaises(ValueError):
                consume_care(item,now=stamp,version=9,witness=witness,side="primary")

    def test_malformed_care_receipt_cannot_authorize(self):
        from skeleton.ai.webcrawler.dragon_vault_care import issue_care,validate_care
        grant=issue_care(operation="a"*64,request_digest="b"*64,snapshot_digest="c"*64,
                         principal_email="owner@example.test",now=NOW,days=1,budget=1)
        for patch in ({"budget":4},{"principal_email":" INVALID "},{"expires_at":NOW+8*DAY},{"used":1},{"network_authorized":True},
                      {"enabled":1},{"issued_at":float("nan")}):
            with self.assertRaises(ValueError):
                validate_care({**grant,**patch})


class CareHistoryTests(unittest.TestCase):
    def test_bounded_history_advances_anchor_without_fabricating_prefix(self):
        from skeleton.ai.webcrawler.dragon_vault_care_history import append_history,public_history,validate_history
        value=None
        for i in range(24):
            value=append_history(value,witness="c"*64,version=i+2,at=NOW+i,kind="grant",
               operation=f"{i:064x}",budget=2,used=0)
        self.assertEqual(value["omitted"],8)
        self.assertEqual(len(value["entries"]),16)
        view=public_history(value,witness="c"*64,version=25)
        self.assertEqual(view["events"][0]["sequence"],9)
        self.assertNotIn("operation",view["events"][0])
        self.assertFalse(view["prefix_unknown"])
        with self.assertRaises(ValueError):
            validate_history({**value,"head":"a"*64},witness="c"*64,version=25)

    def test_repairs_consume_exact_credit_and_withdrawal_closes_grant(self):
        from skeleton.ai.webcrawler.dragon_vault_care_history import append_history
        args={"witness":"c"*64,"operation":"a"*64,"budget":2}
        first=append_history(None,**args,version=7,at=NOW,kind="grant",used=0)
        second=append_history(first,**args,version=8,at=NOW+1,kind="auto_primary",used=1)
        for changes in ({"used":1},{"operation":"b"*64},{"at":NOW-1},{"version":8}):
            with self.assertRaises(ValueError):
                append_history(second,**{**args,"version":9,"at":NOW+2,"kind":"auto_replica","used":2,**changes})
        withdrawn=append_history(second,**{**args,"operation":"b"*64},version=9,at=NOW+2,kind="withdraw",used=0)
        with self.assertRaises(ValueError):
            append_history(withdrawn,**args,version=10,at=NOW+3,kind="auto_replica",used=2)
        legacy=append_history(None,**args,version=9,at=NOW+2,kind="auto_replica",used=2,prefix_unknown=True)
        self.assertTrue(legacy["prefix_unknown"])


class ArchiveRoutingTests(unittest.TestCase):
    def test_scoped_keys_and_index_pipeline(self):
        from skeleton.ai.webcrawler.dragon_archive_routing import query_keys,candidate_pipeline
        keys=query_keys(SCOPE,"Optical magnetometer")
        self.assertEqual(len(keys),2)
        self.assertNotEqual(keys,query_keys({**SCOPE,"owner_id":"other"},"Optical magnetometer"))
        pipeline=candidate_pipeline(SCOPE,keys,NOW)
        self.assertEqual(pipeline[0]["$match"]["owner_id"],SCOPE["owner_id"])
        self.assertEqual(pipeline[-1],{"$limit":65})
        self.assertNotIn("Optical",str(pipeline))

    def test_capacity_expansion_keeps_active_and_window_bounds(self):
        from skeleton.ai.webcrawler.dragon_vault_quota import MAX_RESERVED,quota_lists
        from skeleton.ai.webcrawler.dragon_treasury_vault import MAX_VAULT_SESSIONS,MAX_WINDOW
        self.assertEqual((MAX_VAULT_SESSIONS,MAX_RESERVED,MAX_WINDOW),(1024,1056,32))
        self.assertEqual(len(quota_lists({"vault_ids":[f"c{i}" for i in range(1024)]})[1]),1024)
        with self.assertRaises(ValueError):
            quota_lists({"vault_ids":[f"c{i}" for i in range(1025)]})


if __name__=="__main__":
    unittest.main()
