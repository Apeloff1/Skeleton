"""Hostile recorded-census manipulation tests; no simulated clearance."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v5_anatomical_evidence as check

class CensusEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.record=json.loads(check.RECEIPT.read_bytes())
 def test_actual_record_is_consistent_but_not_collision_qualified(self):
  result=check.verify(self.record)
  self.assertTrue(result["recorded_census_consistent"])
  self.assertEqual(result["exact_pinned_model_receipts"],7)
  self.assertEqual(result["blended_skin_risk_triangles"],171165)
  self.assertFalse(result["continuous_collision_qualified"])
  self.assertFalse(result["actual_models_replayed_in_ci"])
 def test_reclassifying_ambiguous_faces_denied(self):
  self.record["cohort_counts"]["three_way_mixed"]=0
  with self.assertRaisesRegex(ValueError,"untrusted anatomy"):
   check.verify(self.record)
 def test_hiding_mixed_rig_seams_denied(self):
  self.record["triangles_touching_multi_influence_vertices"]=0
  with self.assertRaisesRegex(ValueError,"seams"):
   check.verify(self.record)
 def test_missing_original_model_receipt_denied(self):
  self.record["verified_exact_local_model_runs"].pop()
  with self.assertRaisesRegex(ValueError,"missing measured"):
   check.verify(self.record)
 def test_forged_sha_denied(self):
  self.record["verified_exact_local_model_runs"][0]["sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"source model"):
   check.verify(self.record)
 def test_duplicate_model_denied(self):
  self.record["verified_exact_local_model_runs"][0]=copy.deepcopy(
   self.record["verified_exact_local_model_runs"][1])
  with self.assertRaisesRegex(ValueError,"duplicate"):
   check.verify(self.record)
 def test_false_clearance_denied(self):
  for key in ["continuous_collision_qualified","artist_approved","release_qualified",
              "physical_rtx_verified","optional_equipment_enabled"]:
   r=copy.deepcopy(self.record);r[key]=True
   with self.assertRaisesRegex(ValueError,"must not authorize"):
    check.verify(r)
 def test_fake_full_contact_pairing_denied(self):
  self.record["completed_full_contact_pairings"]=19
  with self.assertRaisesRegex(ValueError,"must not authorize"):
   check.verify(self.record)
if __name__=="__main__":unittest.main()
