"""Temporal archive tests: no network or implicit historic-use authorization."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from skeleton.ai.webcrawler.dragon_revisit_model import ChangeSample, infer_revisit
from skeleton.ai.webcrawler.dragon_treasury import Observation, build_treasury, progression, parse_retained_text

NOW=1_800_000_000.
DAY=86400.
BASE="https://example.org"
A="Orbital navigation instrument report. The original calibration uses 10 degrees and 20 percent efficiency. Retired legacy telemetry."
B="Orbital navigation instrument report. The updated calibration uses 20 degrees and 10 percent efficiency. New current optical telemetry."
C="Orbital navigation instrument report. The future calibration uses 30 degrees and 15 percent efficiency. Revised spectrometer telemetry."


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def obs(session, url, text, time, *, permitted=True, archive=False, variant="", hint=None):
    return Observation(session,digest(session+url+text+str(time)),url,digest(text),time,
                       text if permitted else None, NOW+DAY if permitted else None,
                       "text/plain",variant,hint,True,True,archive)


def treasury(rows, **kwargs):
    return build_treasury(rows,as_of=NOW,growth=1000,**kwargs)


class TreasuryTests(unittest.TestCase):
    def test_current_and_historic_are_disjoint_search_corpora(self):
        old=obs("old",BASE+"/instrument",A,NOW-DAY,archive=True)
        new=obs("new",BASE+"/instrument",B,NOW-3600)
        current=treasury([old,new],mode="current_only",query="legacy")
        historic=treasury([old,new],mode="historic_only",query="legacy")
        self.assertEqual(current["hits"],[])
        self.assertEqual(historic["hits"][0]["source_id"],old.source_id)
        self.assertEqual(historic["current_indexed"],1)
        self.assertEqual(historic["historic_indexed"],1)
        self.assertEqual(historic["verified_historic_transitions"],1)
        self.assertEqual(current["partition_digest"],historic["partition_digest"])
        fid=historic["family_rows"][0]["family_id"]
        comparison=treasury([old,new],mode="compare",family=fid)["comparison"]
        self.assertTrue(comparison["delta"]["numeric_change"])
        self.assertEqual(comparison["current"]["previous_revision_id"],comparison["previous"]["revision_id"])

    def test_withheld_newer_observation_cannot_promote_older_current(self):
        old=obs("old",BASE+"/instrument",A,NOW-DAY)
        held=obs("held",BASE+"/instrument",B,NOW-100,permitted=False)
        result=treasury([old,held],mode="current_only")
        self.assertEqual(result["hits"],[])
        self.assertEqual(result["blocked_current"],1)
        self.assertEqual(result["metadata_only"],1)
        historic=treasury([old,held],mode="historic_only")
        self.assertEqual(historic["hits"][0]["source_id"],old.source_id)
        self.assertFalse(result["evolution"]["hoarder_qualified"])

    def test_newer_unchanged_but_held_keeps_only_authorized_older_reference(self):
        old=obs("old",BASE+"/instrument",A,NOW-DAY,archive=True)
        held=obs("held",BASE+"/instrument",A,NOW-100,permitted=False)
        result=treasury([old,held],mode="historic_only")
        self.assertEqual(result["revisions"],1)
        self.assertEqual(result["current_indexed"],0)
        self.assertEqual(result["historic_indexed"],1)
        row=result["hits"][0]
        self.assertEqual(row["source_id"],old.source_id)
        self.assertEqual(row["indexed_capture_at"],old.captured_at)
        self.assertEqual(row["last_seen"],held.captured_at)
        self.assertTrue(row["latest_observed"])

    def test_alias_blocks_current_but_does_not_grant_access(self):
        old=obs("old",BASE+"/instrument",A,NOW-DAY)
        alias={"url":old.url,"captured_at":NOW-300,"content_hash":digest(B)}
        result=treasury([old],alias_blockers=[alias],mode="current_only")
        self.assertEqual(result["hits"],[])
        self.assertEqual(result["alias_held_families"],1)
        self.assertEqual(result["revisions"],1)
        self.assertEqual(result["verified_historic_transitions"],0)
        historic=treasury([old],alias_blockers=[alias],mode="historic_only")
        self.assertEqual(historic["hits"][0]["source_id"],old.source_id)
        self.assertFalse(historic["hits"][0]["archive_only"])

    def test_same_time_conflict_and_rollback_cycle_not_credited(self):
        old=obs("a",BASE+"/instrument",A,NOW-DAY)
        conflict=obs("b",old.url,B,old.captured_at)
        result=treasury([old,conflict])
        self.assertEqual(result["current_indexed"],0)
        self.assertEqual(result["verified_historic_transitions"],0)
        self.assertTrue(result["family_rows"][0]["simultaneous_conflict"])
        cycle=[obs(str(k),old.url,text,NOW-DAY+3600*k)
               for k,text in enumerate((A,B,A,B))]
        result=treasury(cycle,mode="timeline")
        self.assertEqual(result["rollbacks"],2)
        self.assertEqual(result["verified_historic_transitions"],1)
        self.assertEqual(result["parsed_unique_payloads"],2)
        self.assertEqual(result["revisions"],4)

    def test_representation_variants_do_not_merge(self):
        old=obs("a",BASE+"/instrument",A,NOW-DAY,variant="en")
        new=obs("b",old.url,B,NOW-100,variant="fr")
        result=treasury([old,new])
        self.assertEqual(result["families"],2)
        self.assertEqual(result["current_indexed"],2)
        self.assertEqual(result["verified_historic_transitions"],0)

    def test_evolution_requires_distinct_verified_intergenerational_custody(self):
        rows=[]
        for k in range(4):
            url=BASE+f"/document{k}"
            for n,text in enumerate((A,B,C,C)):
                rows.append(obs(str(n),url,text,NOW-4*DAY+n*DAY))
        value=treasury(rows)
        self.assertEqual(value["verified_historic_transitions"],8)
        self.assertEqual(value["verified_changed_families"],4)
        self.assertEqual(value["evolution"]["form"],"hoarder")
        self.assertEqual(value["evolution"]["level"],60)
        self.assertEqual(treasury(rows,candidate_limit_reached=True)["evolution"]["form"],"archivist")
        self.assertEqual(progression(799,500,qualified=True)["form"],"pathfinder")
        self.assertEqual(progression(800,349,qualified=True)["level"],50)
        self.assertEqual(progression(800,350,qualified=True)["level"],51)

    def test_malformed_held_text_and_capacity_fail_closed(self):
        row=obs("a",BASE+"/instrument",A,NOW-100)
        with self.assertRaises(ValueError):
            treasury([replace(row,usable_until=NOW)])
        with self.assertRaises(ValueError):
            treasury([row,row])
        with self.assertRaises(ValueError):
            treasury([row],alias_blockers=[{"url":row.url,"captured_at":NOW+301,"content_hash":digest(B)}])

    def test_content_defined_parser_is_deterministic_and_numeric_ordered(self):
        left=parse_retained_text(A)
        right=parse_retained_text(B)
        self.assertEqual(left,parse_retained_text(A))
        self.assertNotEqual(left.numbers,right.numbers)
        self.assertLessEqual(len(parse_retained_text(("alpha beta gamma delta "*500)[:24000]).section_hashes),32)


class RevisitTests(unittest.TestCase):
    def model(self, hashes, **kwargs):
        samples=[ChangeSample(NOW-(len(hashes)-i)*DAY,digest(h)) for i,h in enumerate(hashes)]
        return infer_revisit(samples,now=NOW,publisher_due=kwargs.pop("publisher_due",None),
                            allowed=kwargs.pop("allowed",True),**kwargs)

    def test_stable_interval_backs_off_and_changed_interval_tightens(self):
        stable=self.model(["a"]*7)
        changed=self.model(["a","b","c","d","e","f","g"])
        self.assertGreater(stable["interval_seconds"],changed["interval_seconds"])
        self.assertGreater(changed["change_probability_estimate"],stable["change_probability_estimate"])
        self.assertEqual(stable["qualified_intervals"],6)
        self.assertEqual(changed["observed_changes"],6)

    def test_untrusted_publisher_hint_only_postpones_and_denied_never_due(self):
        normal=self.model(["a","b","c"])
        held=self.model(["a","b","c"],publisher_due=NOW+2*DAY,allowed=False)
        self.assertGreaterEqual(held["due_at"],normal["due_at"])
        self.assertFalse(held["ready_for_review"])
        self.assertFalse(held["network_executed"])

    def test_burst_and_conflict_do_not_mint_interval_confidence(self):
        samples=[ChangeSample(NOW-400,digest("a")),ChangeSample(NOW-399,digest("b")),
                 ChangeSample(NOW-100,digest("c")),ChangeSample(NOW-100,digest("d"))]
        value=infer_revisit(samples,now=NOW,publisher_due=None,allowed=True)
        self.assertEqual(value["qualified_intervals"],0)
        self.assertEqual(value["ambiguous_intervals"],1)
        self.assertFalse(value["ready_for_review"])


if __name__=="__main__":
    unittest.main()
