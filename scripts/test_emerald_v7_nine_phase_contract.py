"""Contract tests use actual V7 runner field names and reject forged receipts."""
from __future__ import annotations
import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_emerald_v7_nine_phase as proof
from emerald_v6_crossfade_screen import TRANSITIONS, PAIRS, CROSSFADE_SECONDS, TOOLS

class FullReportContractTests(unittest.TestCase):
    def setUp(self):
        summary=json.loads(proof.DEFAULT.read_bytes())
        self.form=summary["forms"][0]
        near=self.form["near_margin_counts_by_route"]
        rows=[]
        for i,(old,new) in enumerate(TRANSITIONS):
            for j in range(9):
                value=near[i][j]
                rows.append({
                    "from_clip": old, "to_clip": new, "alpha": j/8,
                    "source_old_time_s": .22*(1-j/8),
                    "source_new_time_s": .22*j/8,
                    "new_independent_contact_pairs": 0,
                    "shared_index_bind_seam_candidates": 551,
                    "within_8mm_not_contact": value,
                    "pairs": [
                        {"pair": a+"__"+b,
                         "new_independent_contact_pairs": 0,
                         "shared_index_bind_seam_candidates": (551 if k==0 else 0),
                         "within_8mm_not_contact": (value if k==0 else 0),
                         "candidate_pairs": value+551 if k==0 else 0,
                         "broadphase_visits": value+551 if k==0 else 0}
                        for k,(a,b) in enumerate(PAIRS)]
                })
        self.rows=rows
        self.report={
            "schema": "skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1",
            "stage": self.form["stage"],
            "model_bytes": self.form["bytes"],
            "model_sha256": self.form["sha256"],
            "donor_sha256": proof.DONOR,
            "reviewed_tool_digests": TOOLS.copy(),
            "source_crossfade_seconds": CROSSFADE_SECONDS,
            "steps_per_transition": 9,
            "total_sampled_blends": 54,
            "clip_transitions": [list(x) for x in TRANSITIONS],
            "samples": rows,
            "observed_new_contact_instances": 0,
            "sampled_blends_with_new_contacts": 0,
            "all_transition_intervals_qualified": False,
            "tested_in_real_browser_mixer": False,
            "continuous_collision_qualified": False,
            "unexamined_rig_seams_qualified": False,
            "optional_equipment_enabled": False,
            "artist_approved": False,
            "physical_rtx_verified": False,
            "release_qualified": False,
        }
        self.near=near

    def test_real_runner_field_name_is_accepted(self):
        r=proof.verify_full_report(self.report,self.form,self.near)
        self.assertEqual(r["validated_rows"],54)
        self.assertEqual(r["new_contacts"],0)
        self.assertFalse(r["full_continuous_collision_qualified"])

    def test_exact_legacy_alias_must_be_pinned(self):
        self.report.pop("reviewed_tool_digests")
        self.report["source_tools"]={"contact_audit.py":proof.TOOL}
        r=proof.verify_full_report(self.report,self.form,self.near)
        self.assertEqual(r["near_margin_pairs"],sum(map(sum,self.near)))
        self.report["source_tools"]["contact_audit.py"]="0"*64
        with self.assertRaisesRegex(ValueError,"legacy auditor"):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_contradictory_dual_tool_field_rejected(self):
        self.report["source_tools"]={"contact_audit.py":"0"*64}
        with self.assertRaisesRegex(ValueError,"legacy auditor"):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_import_cache_tool_forgery_rejected(self):
        self.report["reviewed_tool_digests"]["contact_geometry.py"]="0"*64
        with self.assertRaisesRegex(ValueError,"reviewed geometry"):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_incomplete_and_duplicate_poses_rejected(self):
        for change in ("missing","duplicate"):
            report=copy.deepcopy(self.report)
            if change=="missing":report["samples"].pop()
            else:report["samples"][1]=copy.deepcopy(report["samples"][0])
            with self.assertRaises(ValueError):
                proof.verify_full_report(report,self.form,self.near)

    def test_pair_suppression_is_not_silently_cleared(self):
        self.report["samples"][7]["pairs"][0]["within_8mm_not_contact"]=0
        with self.assertRaisesRegex(ValueError,"per-region"):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_attempted_contact_hiding_is_rejected(self):
        self.report["samples"][0]["pairs"][0]["new_independent_contact_pairs"]=1
        with self.assertRaises(ValueError):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_malformed_counter_denied(self):
        self.report["samples"][0]["pairs"][0]["broadphase_visits"]=-1
        with self.assertRaisesRegex(ValueError,"witness count"):
            proof.verify_full_report(self.report,self.form,self.near)

    def test_hardware_release_and_real_browser_forgery_denied(self):
        for flag in ("all_transition_intervals_qualified",
                     "tested_in_real_browser_mixer",
                     "continuous_collision_qualified",
                     "unexamined_rig_seams_qualified",
                     "optional_equipment_enabled",
                     "artist_approved",
                     "physical_rtx_verified",
                     "release_qualified"):
            report=copy.deepcopy(self.report)
            report[flag]=True
            with self.assertRaisesRegex(ValueError,"acceptance"):
                proof.verify_full_report(report,self.form,self.near)

    def test_crossfade_schedule_repin_denied(self):
        self.report["source_crossfade_seconds"]=.30
        with self.assertRaisesRegex(ValueError,"source clip matrix"):
            proof.verify_full_report(self.report,self.form,self.near)

if __name__=="__main__":unittest.main()
