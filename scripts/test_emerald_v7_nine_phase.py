"""Negative-path tests for nine-phase V7 source-bound evidence consistency."""
from __future__ import annotations
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v7_nine_phase as proof

class NinePhaseEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.record=json.loads(proof.DEFAULT.read_bytes())

 def test_source_ledger_consistent_but_not_physical_clearance(self):
  result=proof.verify(self.record)
  self.assertEqual(result["complete_sampled_pose_count"],108)
  self.assertEqual(result["new_contact_witnesses"],0)
  self.assertEqual(result["near_margin_pair_occurrences"],415154)
  self.assertFalse(result["real_three_mixer_qualified"])
  self.assertFalse(result["continuous_collision_qualified"])
  self.assertEqual(result["exact_full_reports_verified"],0)

 def test_unavailable_private_full_receipt_is_not_fake_accepted(self):
  with tempfile.TemporaryDirectory() as folder:
   with self.assertRaisesRegex(ValueError,"full original 54-pose"):
    proof.verify(self.record,Path(folder))

 def test_no_pose_can_be_silently_removed(self):
  self.record["forms"][0]["near_margin_counts_by_route"][2].pop()
  with self.assertRaisesRegex(ValueError,"source pose/phase"):
   proof.verify(self.record)

 def test_source_model_sha_cannot_be_replaced(self):
  self.record["forms"][1]["sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"V7 output identity"):
   proof.verify(self.record)

 def test_source_full_report_digest_cannot_be_replaced(self):
  self.record["forms"][0]["full_report_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"V7 output identity"):
   proof.verify(self.record)

 def test_forged_contact_or_margin_counts_denied(self):
  self.record["forms"][0]["near_margin_counts_by_route"][0][0]=0
  with self.assertRaisesRegex(ValueError,"contact sum"):
   proof.verify(self.record)

 def test_wrong_auditor_or_crossfade_policy_denied(self):
  for item,value in [("auditor_sha256","0"*64),("blend_seconds",.5),("margin_m",.08)]:
   altered=copy.deepcopy(self.record)
   altered[item]=value
   with self.assertRaisesRegex(ValueError,"method"):
    proof.verify(altered)

 def test_falsely_signed_off_continuous_and_release_denied(self):
  for flag in ("all_other_anatomical_pairs_qualified",
               "all_arbitrary_playheads_qualified","continuous_time_collision_qualified",
               "real_three_mixer_qualified","artist_approved","physical_rtx_verified",
               "remote_binary_publication_verified","release_qualified"):
   r=copy.deepcopy(self.record);r[flag]=True
   with self.assertRaisesRegex(ValueError,"falsely elevated"):
    proof.verify(r)

 def test_missing_model_receipt_denied(self):
  self.record["forms"].pop()
  with self.assertRaisesRegex(ValueError,"two distinct"):
   proof.verify(self.record)

if __name__=="__main__":unittest.main()
