"""V6 correction math and fail-closed sampled-pose evidence fixtures.

These are *source and synthetic tests*, not replays of 230MB of private model
binary data, full motion collision, a GPU or artistic approval.
"""
from pathlib import Path
import copy,json,math,tempfile,unittest
import numpy as np
import emerald_v6_tail_clearance as build
import check_emerald_v6_contact_evidence as evidence

class TailCorrectionTests(unittest.TestCase):
 def test_correct_local_y_hamilton_product(self):
  old=np.array([[0.,0.,0.,1.],[0.,0.,1.,0.],[1.,0.,0.,0.]],dtype="<f4")
  original=old.copy()
  result=build.quat_post_y(old)
  s=math.sin(.09);c=math.cos(.09)
  np.testing.assert_allclose(result[0],[0,s,0,c],atol=1e-7)
  np.testing.assert_allclose(result[1],[-s,0,c,0],atol=1e-7)
  np.testing.assert_allclose(np.linalg.norm(result,axis=1),1,atol=1e-7)
  np.testing.assert_array_equal(old,original)

 def test_wrong_angle_cannot_be_used_to_hide_a_failure(self):
  q=np.array([[0.,0.,0.,1.],[0.,0.,1.,0.]],dtype="<f4")
  for angle in (-.18,0.,.01,.36,float("nan")):
   with self.assertRaisesRegex(ValueError,"unapproved yaw"):
    build.quat_post_y(q,angle)

 def test_nonunit_nonfinite_and_invalid_quat_denied(self):
  cases=[np.zeros((2,4)),np.ones((2,3)),
         np.array([[0,0,0,1],[0,float("nan"),0,1.]],dtype="<f4"),
         np.array([[0.,0.,0.,1.]],dtype="<f4")]
  for q in cases:
   with self.assertRaises(ValueError):
    build.quat_post_y(q)

 def test_exact_v5_and_v6_pins_unmodified(self):
  self.assertEqual(build.DONOR,
    "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")
  self.assertEqual(build.JOINT,34)
  self.assertEqual(build.CLIPS,("orbit-01","landing-1"))
  self.assertEqual(set(build.PINNED),{"pathfinder","archivist"})
  self.assertEqual(build.OUTPUTS["pathfinder"][0],114693124)
  self.assertEqual(build.OUTPUTS["archivist"][0],114815776)

 def test_missing_original_model_denied(self):
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp)
   with self.assertRaisesRegex(ValueError,"exact original V5"):
    build.build("pathfinder",t/"missing.glb",t/"candidate.glb")
   self.assertFalse((t/"candidate.glb").exists())

 def test_existing_candidate_never_overwritten(self):
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp)
   original=t/"candidate.glb"
   original.write_bytes(b"existing")
   with self.assertRaisesRegex(ValueError,"trusted unused"):
    build.build("archivist",t/"missing.glb",original)
   self.assertEqual(original.read_bytes(),b"existing")

class SourceRecordedEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.receipt=json.loads(evidence.DEFAULT.read_bytes())
 def test_record_consistent_but_no_release_promotion(self):
  checked=evidence.verify(self.receipt)
  self.assertEqual(checked["sampled_exported_pose_count"],36)
  self.assertEqual(checked["anatomical_pair_instances"],108)
  self.assertEqual(checked["new_independent_contact_occurrences"],0)
  self.assertFalse(checked["cross_clip_transition_qualified"])
  self.assertFalse(checked["original_model_bytes_replayed_by_source_only_tests"])
 def test_forged_zero_near_margin_denied(self):
  self.receipt["forms"][0]["poses"][0]["near_margin_pairs"]=0
  with self.assertRaisesRegex(ValueError,"triangle-distance"):
   evidence.verify(self.receipt)
 def test_missing_source_pose_denied(self):
  self.receipt["forms"][1]["poses"].pop()
  with self.assertRaisesRegex(ValueError,"missing exact exported"):
   evidence.verify(self.receipt)
 def test_unexplained_extra_contact_cannot_be_hidden(self):
  self.receipt["forms"][0]["poses"][3]["new_nonweld_contacts"]=1
  with self.assertRaisesRegex(ValueError,"triangle-distance"):
   evidence.verify(self.receipt)
 def test_inherited_attachment_seams_not_pretend_safe(self):
  self.receipt["original_welded_contact_pairs_are_safety_approved"]=True
  with self.assertRaisesRegex(ValueError,"falsely promoted"):
   evidence.verify(self.receipt)
 def test_false_art_device_transition_release_flags_denied(self):
  for flag in ("continuous_motion_intervals_qualified",
               "cross_clip_transition_qualified","artistic_approved",
               "physical_rtx_verified","release_qualified"):
   r=copy.deepcopy(self.receipt)
   r[flag]=True
   with self.assertRaisesRegex(ValueError,"falsely promoted"):
    evidence.verify(r)
 def test_missing_or_duplicated_clip_fraction_denied(self):
  self.receipt["forms"][0]["poses"][1]=copy.deepcopy(self.receipt["forms"][0]["poses"][0])
  with self.assertRaisesRegex(ValueError,"duplicated pose"):
   evidence.verify(self.receipt)

if __name__=="__main__":
 unittest.main()
