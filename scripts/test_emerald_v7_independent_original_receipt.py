"""Reject altered source-bound original donor evidence and false launch flags."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v7_independent_original_receipt as proof

class OriginalModelLedgerTests(unittest.TestCase):
 def setUp(self):
  self.doc=json.loads(proof.DEFAULT.read_bytes())

 def test_recorded_four_archives_preserve_no_release(self):
  out=proof.verify(self.doc)
  self.assertEqual(out["recorded_original_v6_v7_zip_count"],4)
  self.assertTrue(out["one_reviewed_160_key_tail_track_per_v7_form"])
  self.assertFalse(out["actual_four_zips_replayed_by_source_only_ci"])
  self.assertFalse(out["release_qualified"])

 def test_corrupt_zip_digest_denied(self):
  self.doc["models"][0]["v6"]["zip_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"digest differs"):
   proof.verify(self.doc)

 def test_wrong_original_glb_byte_size_denied(self):
  self.doc["models"][1]["v7"]["bytes"]+=1
  with self.assertRaisesRegex(ValueError,"digest differs"):
   proof.verify(self.doc)

 def test_wrong_original_embedded_bin_prefix_denied(self):
  self.doc["models"][0]["original_binary_prefix_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"model prefix"):
   proof.verify(self.doc)

 def test_nonreviewed_161_key_change_denied(self):
  self.doc["models"][0]["modified_keyframes"]=161
  with self.assertRaisesRegex(ValueError,"160-key"):
   proof.verify(self.doc)

 def test_absent_original_stage_denied(self):
  self.doc["models"].pop()
  with self.assertRaisesRegex(ValueError,"missing or repeated"):
   proof.verify(self.doc)

 def test_forged_physical_or_git_publication_denied(self):
  for flag in ("full_continuous_collision_qualified","artist_approved",
               "physical_rtx_verified","remote_git_binary_verified","release_qualified"):
   doc=copy.deepcopy(self.doc);doc[flag]=True
   with self.assertRaisesRegex(ValueError,"fake physical"):
    proof.verify(doc)

if __name__=="__main__":unittest.main()
