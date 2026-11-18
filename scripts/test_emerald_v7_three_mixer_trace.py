"""Fail-closed V7 Three 0.186 source trace and original-skinned contact bridge tests.

Synthetic tests never constitute original model byte proof or real GPU rendering.
"""
from __future__ import annotations
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v7_three_mixer_trace as traces
import qualify_emerald_v7_three_trace_contacts as qualification

ROUTES=traces.TRANSITIONS
FAKE_SHA=traces.PINS["pathfinder"][1]

def synthetic(steps=3):
 original={
  "schema":"skeleton.emerald.v7.actual-three-mixer-joints.v1",
  "stage":"pathfinder",
  "model_bytes":traces.PINS["pathfinder"][0],
  "model_sha256":FAKE_SHA,
  "donor_sha256":traces.DONOR,
  "three_revision":"186",
  "mixer":"THREE.AnimationMixer and AnimationAction.crossFadeFrom (warp=false)",
  "source_stage_fade_seconds":.22,
  "samples_per_route":steps,
  "total_sampled_poses":steps*6,
  "skin_joints":108,
  "geometry_collision_scanned":False,
  "physical_webgl_tested":False,
  "real_browser_playheads_qualified":False,
  "continuous_collision_qualified":False,
  "all_anatomical_pairs_qualified":False,
  "artist_approved":False,
  "physical_rtx_verified":False,
  "release_qualified":False,
  "routes":[],
 }
 world=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
 for old,new in ROUTES:
  rows=[]
  for i in range(steps):
   a=i/(steps-1)
   rows.append({
    "from_clip":old,"to_clip":new,"alpha":a,
    "source_old_time_s":.78+a*.22,
    "source_new_time_s":a*.22,
    "outgoing_weight":1-a,"incoming_weight":a,
    "joints":[{"joint":j,"local_translation":[0.,0.,0.],
               "local_quaternion":[0.,0.,0.,1.],
               "world_matrix":world[:]} for j in range(108)],
   })
  original["routes"].append({"from_clip":old,"to_clip":new,
                             "outgoing_duration_s":1.,
                             "incoming_duration_s":1.,
                             "samples":rows})
 return original

class ActualThreeTraceContractTests(unittest.TestCase):
 def setUp(self):self.report=synthetic()
 def test_exact_108_joint_synthetic_shape_never_claims_collisions(self):
  checked=traces.verify(self.report,"pathfinder")
  self.assertEqual(checked["sampled_poses"],18)
  self.assertFalse(checked["full_model_sha_independently_rechecked"])
  self.assertFalse(checked["source_geometry_contacts_checked"])
  self.assertFalse(checked["release_qualified"])
 def test_wrong_three_version_and_source_digest_denied(self):
  for key,value in (("three_revision","185"),("model_sha256","0"*64),
                    ("source_stage_fade_seconds",.3)):
   data=copy.deepcopy(self.report);data[key]=value
   with self.assertRaisesRegex(ValueError,"source donor"):
    traces.verify(data,"pathfinder")
 def test_missing_one_real_joint_denied(self):
  self.report["routes"][0]["samples"][0]["joints"].pop()
  with self.assertRaisesRegex(ValueError,"full 108-joint"):
   traces.verify(self.report,"pathfinder")
 def test_duplicate_motion_sample_denied(self):
  rows=self.report["routes"][0]["samples"]
  rows[1]=copy.deepcopy(rows[0])
  with self.assertRaisesRegex(ValueError,"phase"):
   traces.verify(self.report,"pathfinder")
 def test_unbound_action_weights_denied(self):
  self.report["routes"][0]["samples"][1]["incoming_weight"]=2
  with self.assertRaisesRegex(ValueError,"action weight"):
   traces.verify(self.report,"pathfinder")
 def test_incomplete_crossfade_weight_denied(self):
  self.report["routes"][0]["samples"][1]["outgoing_weight"]=0
  with self.assertRaisesRegex(ValueError,"not complementary"):
   traces.verify(self.report,"pathfinder")
 def test_false_mixer_phase_is_not_accepted_with_valid_weights(self):
  self.report["routes"][0]["samples"][1]["source_old_time_s"]+=.1
  with self.assertRaisesRegex(ValueError,"outgoing source playhead"):
   traces.verify(self.report,"pathfinder")

 def test_false_incoming_action_phase_rejected(self):
  self.report["routes"][0]["samples"][1]["source_new_time_s"]+=.05
  with self.assertRaisesRegex(ValueError,"incoming source playhead"):
   traces.verify(self.report,"pathfinder")

 def test_complementary_but_wrong_fade_easing_rejected(self):
  record=self.report["routes"][0]["samples"][1]
  record["incoming_weight"]=.9
  record["outgoing_weight"]=.1
  with self.assertRaisesRegex(ValueError,"fade weights deviate"):
   traces.verify(self.report,"pathfinder")

 def test_nonunit_quaternion_denied(self):
  self.report["routes"][0]["samples"][0]["joints"][34]["local_quaternion"]=[0,0,0,0]
  with self.assertRaisesRegex(ValueError,"unnormalized"):
   traces.verify(self.report,"pathfinder")
 def test_nonfinite_matrix_denied(self):
  self.report["routes"][0]["samples"][0]["joints"][0]["world_matrix"][12]=float("nan")
  with self.assertRaisesRegex(ValueError,"nonfinite"):
   traces.verify(self.report,"pathfinder")
 def test_corrupt_world_affine_last_row_denied(self):
  self.report["routes"][0]["samples"][0]["joints"][0]["world_matrix"][15]=0
  with self.assertRaisesRegex(ValueError,"world matrix"):
   traces.verify(self.report,"pathfinder")
 def test_original_model_byte_recheck_refuses_synthetic_file(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/"not-original.glb";path.write_bytes(b"not a real model")
   with self.assertRaisesRegex(ValueError,"SHA recheck failed"):
    traces.verify(self.report,"pathfinder",path)
 def test_no_claim_of_equipment_browser_ccd_art_rtx_release(self):
  for flag in ("geometry_collision_scanned","physical_webgl_tested",
               "real_browser_playheads_qualified","continuous_collision_qualified",
               "all_anatomical_pairs_qualified","artist_approved",
               "physical_rtx_verified","release_qualified"):
   data=copy.deepcopy(self.report);data[flag]=True
   with self.assertRaisesRegex(ValueError,"falsely claims"):
    traces.verify(data,"pathfinder")

class ReplayedCheckpointIntegrityTests(unittest.TestCase):
 def setUp(self):
  self.area=tempfile.TemporaryDirectory()
  self.addCleanup(self.area.cleanup)
  self.directory=Path(self.area.name)
  self.trace=self.directory/"trace.json"
  self.trace.write_text('{"synthetic_only":true}')
  self.checkpoint=self.directory/"source-prefix.json"
  self.poses=[
      {"from_clip":"orbit-01","to_clip":"orbit-02",
       "alpha":i,"joints":[]} for i in (0,1)]
  self.report={"routes":[{"samples":self.poses}],
               "total_sampled_poses":2,"three_revision":"186"}
  self.pairs=[
      {"pair":a+"__"+b,"new_independent_contact_pairs":0,
       "within_8mm_not_contact":2 if k==0 else 0,
       "shared_index_bind_seam_candidates":1 if k==0 else 0,
       "candidate_pairs":2,"broadphase_visits":4}
      for k,(a,b) in enumerate(qualification.geometry.PAIRS)]
  self.measured={
      "new_independent_contact_pairs":0,
      "within_8mm_not_contact":2,
      "shared_index_bind_seam_candidates":1,
      "pairs":self.pairs,
  }
  class Model:
   def geometry(self):return {"original":"synthetic"}
   def close(self):pass
  class Auditor:
   def GLB(self,*args):return Model()
  self.auditor=Auditor()

 def source_patches(self):
  return [
   patch.object(qualification,"reviewed_input",
                return_value=(self.report,self.auditor,object())),
   patch.object(qualification.geometry,"anatomy",return_value={}),
   patch.object(qualification,"posed_vertices_from_trace",return_value=(None,0.)),
   patch.object(qualification.geometry,"contact_check",
                return_value=self.measured),
  ]

 def test_saved_checkpoint_cannot_skip_remeasurement(self):
  original={"sample_index":0,"from_clip":"orbit-01","to_clip":"orbit-02",
            "alpha":0,"max_mixer_world_matrix_error":0.,**self.measured}
  forged=copy.deepcopy(original)
  forged["within_8mm_not_contact"]=1
  qualification.save_journal(
      self.checkpoint,FAKE_SHA,qualification.digest(self.trace),[forged],2)
  patches=self.source_patches()
  for current in patches:current.start()
  try:
   with self.assertRaisesRegex(ValueError,"remeasured exact original geometry"):
    qualification.evaluate("pathfinder",self.directory/"model.glb",self.directory,
                           self.trace,time_budget=60,
                           checkpoint=self.checkpoint,resume=True)
  finally:
   for current in reversed(patches):current.stop()
  self.assertEqual(json.loads(self.checkpoint.read_bytes())["samples"],[forged])

 def test_exact_saved_prefix_must_be_replayed_and_extended(self):
  row={"sample_index":0,"from_clip":"orbit-01","to_clip":"orbit-02",
       "alpha":0,"max_mixer_world_matrix_error":0.,**self.measured}
  qualification.save_journal(
      self.checkpoint,FAKE_SHA,qualification.digest(self.trace),[row],2)
  patches=self.source_patches()
  for current in patches:current.start()
  try:
   result=qualification.evaluate("pathfinder",self.directory/"model.glb",
                                 self.directory,self.trace,time_budget=60,
                                 checkpoint=self.checkpoint,resume=True)
  finally:
   for current in reversed(patches):current.stop()
  self.assertEqual(result["sampled_poses"],2)
  self.assertEqual(result["new_independent_contact_occurrences"],0)
  self.assertTrue(result["checkpoint_prefix_reexecuted_against_original_geometry"])
  self.assertEqual(len(json.loads(self.checkpoint.read_bytes())["samples"]),2)

class ActualThreeContactOracleTests(unittest.TestCase):
 def setUp(self):
  self.g={"parents":np.array([-1]+[i-1 for i in range(1,108)],dtype=np.int32)}
  self.q=np.repeat([[0.,0.,0.,1.]],108,axis=0)
  self.t=np.zeros((108,3),dtype=np.float64)
 def test_three_world_matrix_is_independently_composed(self):
  world=qualification.independent_world_matrices(self.g,self.t,self.q)
  self.assertEqual(world.shape,(108,4,4))
  np.testing.assert_allclose(world,np.repeat(np.eye(4)[None],108,axis=0))
 def test_real_world_matrix_and_cpu_skin_are_checked(self):
  matrices=np.repeat(np.eye(4)[None],108,axis=0)
  entries=[{"joint":i,
            "local_translation":self.t[i].tolist(),
            "local_quaternion":self.q[i].tolist(),
            "world_matrix":matrices[i].T.reshape(-1).tolist()}
           for i in range(108)]
  with patch.object(qualification.geometry,"skin",
                    return_value=np.zeros((365997,3),dtype=np.float64)):
   result,err=qualification.posed_vertices_from_trace(self.g,entries)
  self.assertEqual(result.shape,(365997,3))
  self.assertLess(err,1e-12)
 def test_tampered_mixer_world_matrix_is_rejected_before_contacts(self):
  matrices=np.repeat(np.eye(4)[None],108,axis=0)
  entries=[{"joint":i,"local_translation":[0.,0.,0.],
            "local_quaternion":[0.,0.,0.,1.],
            "world_matrix":matrices[i].T.reshape(-1).tolist()}
           for i in range(108)]
  entries[34]["world_matrix"][12]=.04
  with self.assertRaisesRegex(ValueError,"matrix hierarchy"):
   qualification.posed_vertices_from_trace(self.g,entries)
 def test_bad_joint_parent_source_tree_denied(self):
  self.g["parents"][34]=34
  with self.assertRaisesRegex(ValueError,"rig cannot"):
   qualification.independent_world_matrices(self.g,self.t,self.q)
 def test_checkpoint_preserves_source_hash_and_unqualified_state(self):
  sample={"from_clip":"orbit-01","to_clip":"orbit-02","alpha":0}
  pairnames=[a+"__"+b for a,b in qualification.geometry.PAIRS]
  row={"sample_index":0,**sample,
       "new_independent_contact_pairs":0,"within_8mm_not_contact":15,
       "max_mixer_world_matrix_error":0.,
       "pairs":[{"pair":name} for name in pairnames]}
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/"checkpoint.json"
   qualification.save_journal(path,FAKE_SHA,"a"*64,[row],3)
   record=json.loads(path.read_bytes())
   self.assertEqual(record["remaining_source_pose_count"],2)
   self.assertFalse(record["continuous_collision_qualified"])
   self.assertEqual(qualification.journal_contract(record,FAKE_SHA,"a"*64,
                     [sample,{"from_clip":"x","to_clip":"y","alpha":.5}]),[row])
   altered=copy.deepcopy(record);altered["actual_three_trace_sha256"]="b"*64
   with self.assertRaisesRegex(ValueError,"wrong exact sources"):
    qualification.journal_contract(altered,FAKE_SHA,"a"*64,[sample])

if __name__=="__main__":
 unittest.main()
