"""Hostile two-stage actual Three source/triangle report admission tests.

No test uses a real model GLB; no synthetic source is allowed to claim device,
continuous collision, artwork or release readiness.
"""
from __future__ import annotations
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import admit_emerald_v7_three_mixer_pair as gate

def fixture(stage="pathfinder"):
 sample_rows=[];poses=[]
 for left,right in gate.traces.TRANSITIONS:
  route=[]
  for j in range(9):
   alpha=j/8
   route.append({"from_clip":left,"to_clip":right,"alpha":alpha})
   index=len(sample_rows)
   candidates=[
      {"pair":a+"__"+b,"new_independent_contact_pairs":0,
       "shared_index_bind_seam_candidates":(551 if k==0 else 0),
       "within_8mm_not_contact":(100 if k==0 else 0),
       "candidate_pairs":100,"broadphase_visits":150}
      for k,(a,b) in enumerate(gate.original.PAIRS)]
   sample_rows.append({
     "sample_index":index,"from_clip":left,"to_clip":right,
     "alpha":alpha,"max_mixer_world_matrix_error":1e-7,
     "new_independent_contact_pairs":0,
     "shared_index_bind_seam_candidates":551,
     "within_8mm_not_contact":100,"pairs":candidates,
   })
  poses.append({"from_clip":left,"to_clip":right,"samples":route})
 trace={"samples_per_route":9,"total_sampled_poses":54,
        "routes":poses}
 report={
  "schema":gate.CONTACT_SCHEMA,"stage":stage,
  "original_model_sha256":gate.traces.PINS[stage][1],
  "actual_three_trace_sha256":"a"*64,
  "three_revision":"186","source_crossfade_seconds":.22,
  "sampled_poses":54,"sampled_anatomical_pair_count":3,
  "reviewed_tool_sha256":gate.original.TOOLS,
  "all_sampled_source_routes_processed":True,
  "all_anatomical_pairs_qualified":False,
  "arbitrary_real_browser_playheads_qualified":False,
  "continuous_collision_qualified":False,
  "physical_webgl_tested":False,"artist_approved":False,
  "physical_rtx_verified":False,"release_qualified":False,
  "new_independent_contact_occurrences":0,
  "near_margin_pair_occurrences":5400,
  "preexisting_bind_seam_occurrences":29754,
  "samples":sample_rows,
 }
 return trace,report

class OriginalTwoStageTraceTests(unittest.TestCase):
 def setUp(self):
  self.trace,self.contact=fixture()
 def test_complete_source_paired_receipt_is_sampled_only(self):
  row=gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
  self.assertEqual(row["original_three_poses_checked"],54)
  self.assertEqual(row["new_independent_contact_occurrences"],0)
  self.assertEqual(row["unqualified_8mm_near_margin_occurrences"],5400)
  self.assertFalse(row["full_continuous_collision_qualified"])
  self.assertFalse(row["release_qualified"])
  self.assertFalse(row["source_triangle_contacts_reexecuted_by_this_gate"])
 def test_duplicate_joint_pose_reference_denied(self):
  self.contact["samples"][10]["alpha"]=self.contact["samples"][9]["alpha"]
  with self.assertRaisesRegex(ValueError,"bound to its exact"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_wrong_source_model_hash_denied(self):
  self.contact["original_model_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"wrong source-mixer"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_missing_anatomical_pair_denied(self):
  self.contact["samples"][0]["pairs"].pop()
  with self.assertRaisesRegex(ValueError,"missing, duplicated"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_independent_positive_collision_retained(self):
  first=self.contact["samples"][0]
  first["pairs"][2]["new_independent_contact_pairs"]=1
  first["new_independent_contact_pairs"]=1
  self.contact["new_independent_contact_occurrences"]=1
  result=gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
  self.assertEqual(result["new_independent_contact_occurrences"],1)
  self.assertFalse(result["sampled_three_mixer_contacts_clear"])
 def test_uncorroborated_contact_count_denied(self):
  self.contact["new_independent_contact_occurrences"]=0
  self.contact["samples"][0]["pairs"][2]["new_independent_contact_pairs"]=1
  with self.assertRaisesRegex(ValueError,"reconcile"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_fake_0_22_mixer_duration_denied(self):
  self.contact["source_crossfade_seconds"]=.5
  with self.assertRaisesRegex(ValueError,"wrong source-mixer"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_fake_actual_gpu_and_device_flags_denied(self):
  for flag in ("all_anatomical_pairs_qualified",
               "arbitrary_real_browser_playheads_qualified",
               "continuous_collision_qualified","physical_webgl_tested",
               "artist_approved","physical_rtx_verified","release_qualified"):
   altered=copy.deepcopy(self.contact);altered[flag]=True
   with self.assertRaisesRegex(ValueError,"attempts full continuous"):
    gate.verify_contact(altered,"pathfinder",self.trace,"a"*64)
 def test_bad_world_matrix_is_not_accepted(self):
  self.contact["samples"][0]["max_mixer_world_matrix_error"]=.001
  with self.assertRaisesRegex(ValueError,"world matrices differ"):
   gate.verify_contact(self.contact,"pathfinder",self.trace,"a"*64)
 def test_missing_original_glbs_denied(self):
  with tempfile.TemporaryDirectory() as directory:
   with self.assertRaisesRegex(ValueError,"missing exact 114MB"):
    gate.model_pin(Path(directory),"pathfinder")
   with self.assertRaisesRegex(ValueError,"trusted unused"):
    output=Path(directory)/"receipt.json"
    output.write_text("protected")
    gate.admit(Path(directory),Path(directory),Path(directory),output)

if __name__=="__main__":
 unittest.main()
