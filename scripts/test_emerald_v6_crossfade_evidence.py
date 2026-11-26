"""Independent receipt-integrity negatives; no synthesized clearance evidence."""
import copy
import unittest

from emerald_v6_crossfade_screen import (
 DONOR,MODELS,TOOLS,TRANSITIONS,PAIRS,CROSSFADE_SECONDS,
)
from verify_emerald_v6_crossfade_evidence import verify

class TransitionEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.stage="pathfinder"
  self.steps=3
  self.rows=[]
  for left,right in TRANSITIONS:
   for k in range(self.steps):
    self.rows.append({
     "from_clip":left,"to_clip":right,"alpha":k/(self.steps-1),
     "new_independent_contact_pairs":0,
     "shared_index_bind_seam_candidates":2,
     "within_8mm_not_contact":4,
     "pairs":[{
       "pair":a+"__"+b,"new_independent_contact_pairs":0,
       "shared_index_bind_seam_candidates":2 if i==0 else 0,
       "within_8mm_not_contact":4 if i==0 else 0,
       "candidate_pairs":6,
      } for i,(a,b) in enumerate(PAIRS)]
    })
  self.report={
   "schema":"skeleton.emerald.v6.crossfade-mesh-screen.v1",
   "stage":self.stage,
   "model_bytes":MODELS[self.stage][0],
   "model_sha256":MODELS[self.stage][1],
   "donor_sha256":DONOR,
   "reviewed_tool_digests":TOOLS,
   "source_crossfade_seconds":CROSSFADE_SECONDS,
   "clip_transitions":[list(x) for x in TRANSITIONS],
   "steps_per_transition":self.steps,
   "total_sampled_blends":len(self.rows),
   "samples":self.rows,
   "observed_new_contact_instances":0,
   "sampled_blends_with_new_contacts":0,
   "all_transition_intervals_qualified":False,
   "tested_in_real_browser_mixer":False,
   "continuous_collision_qualified":False,
   "unexamined_rig_seams_qualified":False,
   "optional_equipment_enabled":False,
   "artist_approved":False,
   "physical_rtx_verified":False,
   "release_qualified":False,
  }

 def test_source_consistency_never_elevates_equipment_or_device(self):
  r=verify(self.report,self.stage)
  self.assertEqual(r["sampled_blends"],18)
  self.assertFalse(r["continuous_collision_qualified"])
  self.assertFalse(r["real_three_mixer_qualified"])
  self.assertFalse(r["release_qualified"])

 def test_positive_collisions_are_retained_as_witnesses(self):
  self.report["samples"][4]["new_independent_contact_pairs"]=3
  self.report["samples"][4]["pairs"][2]["new_independent_contact_pairs"]=3
  self.report["observed_new_contact_instances"]=3
  self.report["sampled_blends_with_new_contacts"]=1
  r=verify(self.report,self.stage)
  self.assertEqual(r["new_contact_occurrences"],3)
  self.assertEqual(r["sampled_blends_with_witnesses"],1)

 def test_missing_transition_sample_rejected(self):
  self.report["samples"].pop()
  with self.assertRaisesRegex(ValueError,"truncated"):
   verify(self.report,self.stage)

 def test_duplicate_or_reordered_transition_denied(self):
  self.report["samples"][1]=copy.deepcopy(self.report["samples"][0])
  with self.assertRaisesRegex(ValueError,"reordered"):
   verify(self.report,self.stage)

 def test_extra_contact_suppressed_by_aggregate_denied(self):
  self.report["samples"][0]["new_independent_contact_pairs"]=1
  self.report["samples"][0]["pairs"][1]["new_independent_contact_pairs"]=1
  with self.assertRaisesRegex(ValueError,"aggregate"):
   verify(self.report,self.stage)

 def test_original_model_repin_denied(self):
  self.report["model_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"untrusted exact-model"):
   verify(self.report,self.stage)

 def test_fake_actual_browser_validation_denied(self):
  self.report["tested_in_real_browser_mixer"]=True
  with self.assertRaisesRegex(ValueError,"false complete"):
   verify(self.report,self.stage)

 def test_false_hardware_or_art_acceptance_denied(self):
  for flag in ("all_transition_intervals_qualified",
               "continuous_collision_qualified","unexamined_rig_seams_qualified",
               "optional_equipment_enabled","artist_approved",
               "physical_rtx_verified","release_qualified"):
   report=copy.deepcopy(self.report)
   report[flag]=True
   with self.assertRaisesRegex(ValueError,"false complete"):
    verify(report,self.stage)

if __name__=="__main__":
 unittest.main()
