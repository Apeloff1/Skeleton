"""Source-only adversarial V7 Three-vs-SLERP pose parity tests.

Synthetic 108-joint arrays never confer original GLB provenance or clearance.
"""
from __future__ import annotations
import copy
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import compare_emerald_v7_three_source_parity as parity

def original_pose():
 translations=np.zeros((108,3),dtype=np.float64)
 quaternions=np.zeros((108,4),dtype=np.float64)
 quaternions[:,3]=1
 traced=[{"joint":i,"local_translation":translations[i].tolist(),
          "local_quaternion":quaternions[i].tolist()} for i in range(108)]
 return translations,quaternions,traced

class V7ThreeSourceParityTests(unittest.TestCase):
 def test_source_pose_delta_is_exact_at_identity(self):
  t,q,poses=original_pose()
  angle,meters=parity.source_pose_delta(t,q,poses)
  self.assertEqual(angle.shape,(108,))
  self.assertAlmostEqual(float(angle.max()),0,places=12)
  self.assertAlmostEqual(float(meters.max()),0,places=12)

 def test_antipodal_quaternions_are_same_orientation(self):
  t,q,poses=original_pose()
  for row in poses:
   row["local_quaternion"]=[0.,0.,0.,-1.]
  angle,dist=parity.source_pose_delta(t,q,poses)
  self.assertLess(float(angle.max()),1e-8)
  self.assertEqual(float(dist.max()),0.)

 def test_tail_root_nonmatching_rotation_has_measurable_witness(self):
  t,q,poses=original_pose()
  radians=.35
  poses[34]["local_quaternion"]=[0,math.sin(radians/2),0,math.cos(radians/2)]
  angle,dist=parity.source_pose_delta(t,q,poses)
  self.assertAlmostEqual(float(angle[34]),radians,places=6)
  self.assertEqual(float(dist.max()),0.)
  self.assertGreater(float(angle[34]),parity.MAX_ANGLE_RAD)

 def test_tail_root_translation_drift_is_not_hidden_by_rotation(self):
  t,q,poses=original_pose()
  poses[34]["local_translation"]=[.011,0,0]
  angle,dist=parity.source_pose_delta(t,q,poses)
  self.assertLess(float(angle.max()),1e-8)
  self.assertAlmostEqual(float(dist[34]),.011,places=9)
  self.assertGreater(float(dist[34]),parity.MAX_TRANSLATION_M)

 def test_missing_or_reordered_original_joint_rejected(self):
  t,q,poses=original_pose()
  with self.assertRaisesRegex(ValueError,"108-joint"):
   parity.source_pose_delta(t,q,poses[:-1])
  poses[22]["joint"]=23
  with self.assertRaisesRegex(ValueError,"Three joint order"):
   parity.source_pose_delta(t,q,poses)

 def test_nonunit_or_nonfinite_source_quaternion_denied(self):
  t,q,poses=original_pose()
  poses[6]["local_quaternion"]=[0,0,0,2]
  with self.assertRaisesRegex(ValueError,"not normalized"):
   parity.source_pose_delta(t,q,poses)
  poses[6]["local_quaternion"]=[0,0,float("nan"),1]
  with self.assertRaisesRegex(ValueError,"joint order"):
   parity.source_pose_delta(t,q,poses)

 def test_wrong_shape_source_cannot_compare(self):
  t,q,poses=original_pose()
  with self.assertRaisesRegex(ValueError,"108-joint"):
   parity.source_pose_delta(t[:-1],q,poses)
  with self.assertRaisesRegex(ValueError,"108-joint"):
   parity.source_pose_delta(t,q[:,:3],poses)

 def test_source_phase_is_actual_mixer_playhead_not_invented(self):
  calls=[]
  q=np.zeros((108,4),dtype=np.float64);q[:,3]=1
  t0=np.zeros((108,3),dtype=np.float64)
  t1=np.full((108,3),.5,dtype=np.float64)
  def sample(_model,_geometry,name,seconds):
   calls.append((name,seconds))
   return 1.0, t0 if name=="orbit-01" else t1,q
  pose={"alpha":.5,"source_old_time_s":.89,
        "source_new_time_s":.11}
  with patch.object(parity.reference,"local_pose",side_effect=sample),\
       patch.object(parity.reference,"slerp_rows",return_value=q):
   t,new_q=parity.phase_reference(None,{},("orbit-01","orbit-02"),pose)
  self.assertEqual(calls,[("orbit-01",.89),("orbit-02",.11)])
  self.assertTrue(np.allclose(t,.25))
  np.testing.assert_array_equal(new_q,q)

 def test_unsupported_stage_refuses_original_model_path(self):
  with self.assertRaisesRegex(ValueError,"unsupported V7"):
   parity.analyze("hoarder",Path("/missing"),Path("/missing"),Path("/missing"))

 def test_missing_binary_original_cannot_use_forged_trace(self):
  with tempfile.TemporaryDirectory() as directory:
   fake=Path(directory)/"pathfinder.glb"
   fake.write_bytes(b"tiny mock is not an original")
   with self.assertRaisesRegex(ValueError,"model bytes differ"):
    parity.analyze("pathfinder",fake,Path("/missing"),Path("/missing"))

 def test_all_runtime_artistic_and_release_holds_default_off(self):
  self.assertEqual(parity.REVIEWED_JOINTS,108)
  self.assertEqual(parity.SAMPLES,54)
  self.assertLess(parity.MAX_ANGLE_RAD,.01)
  self.assertEqual(parity.MAX_TRANSLATION_M,.005)
  self.assertEqual(parity.SCHEMA,
                   "skeleton.emerald.v7.actual-three-versus-source-slerp.v1")

if __name__=="__main__":
 unittest.main()
