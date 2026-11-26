"""Source-only hostile V7 evidence tests; not an original-GLB replay."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v7_evidence as check

class V7EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.r=json.loads(check.DEFAULT.read_bytes())

 def test_real_source_record_explicitly_held(self):
  result=check.verify(self.r)
  self.assertEqual(result["original_witnesses"],20)
  self.assertEqual(result["new_v7_witnesses"],0)
  self.assertEqual(result["total_sampled_blends"],36)
  self.assertEqual(result["remaining_near_margin_pairs"],139465)
  self.assertFalse(result["real_exported_models_rerun_in_source_ci"])
  self.assertFalse(result["real_three_mixer_qualified"])

 def test_pretend_no_near_margin_pairs_is_denied(self):
  self.r["total_near_margin_pair_occurrences"]=0
  with self.assertRaisesRegex(ValueError,"contact counts"):check.verify(self.r)

 def test_other_model_digest_denied(self):
  self.r["forms"][1]["v7_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"exact exported"):check.verify(self.r)

 def test_wrong_source_v6_digest_denied(self):
  self.r["forms"][0]["source_v6_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"exact exported"):check.verify(self.r)

 def test_lost_unqualified_pose_denied(self):
  self.r["forms"][0]["poses_sampled"]=17
  with self.assertRaisesRegex(ValueError,"pose witnesses"):check.verify(self.r)

 def test_fabricated_automatic_equipment_or_hardware_denied(self):
  for name in ("all_anatomical_pairs_qualified","all_crossfade_loop_phases_qualified",
               "continuous_motion_intervals_qualified","real_three_mixer_qualified",
               "optional_equipment_enabled","artist_approved","physical_rtx_verified",
               "release_qualified"):
   altered=copy.deepcopy(self.r)
   altered[name]=True
   with self.assertRaisesRegex(ValueError,"falsely promotes"):
    check.verify(altered)

 def test_renamed_clip_cannot_be_silently_accepted(self):
  self.r["forms"][0]["corrected_animation"]="orbit-03"
  with self.assertRaisesRegex(ValueError,"exact exported"):check.verify(self.r)

 def test_shared_vertex_attachment_seams_are_not_silently_cleared(self):
  self.r["total_preexisting_shared_index_seam_occurrences"]=0
  with self.assertRaisesRegex(ValueError,"contact counts"):check.verify(self.r)

if __name__=="__main__":unittest.main()
