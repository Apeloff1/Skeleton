import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_emerald_unreal_v4_receipt as proof
import publish_emerald_poster_v4 as publication

class NativeEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.manifest=publication.load()[0]
  self.run="f"*32
  self.receipt={"schema":proof.SCHEMA,"run_id":self.run,"engine_editor_imported":True,
   "engine_compiled":False,"physical_rtx_verified":False,"artist_approved":False,
   "release_qualified":False,"engine_version":"5.5.0-test-placeholder",
   "models":[{"stage":x["stage"],"source_sha256":x["sha256"],"source_bytes":x["bytes"],
    "animation_count":381,"skeletal_mesh":"/Game/EmeraldV4/Qualification/"+x["stage"]+"_receipt",
    "skeleton":"/Game/EmeraldV4/Skeleton","imported_paths":["/Game/EmeraldV4/"+str(i) for i in range(382)],
    "artist_approved":False} for x in self.manifest["forms"]]}
 def verify(self):return proof.verify(self.receipt,self.manifest,self.run)
 def test_contract_only_never_hardware_evidence(self):
  q=self.verify()
  self.assertTrue(q["model_imports_consistent"])
  self.assertFalse(q["physical_rtx_verified"])
  self.assertFalse(q["engine_compiled_independently"])
  self.assertFalse(q["artist_approved"])
 def test_fabricated_gpu_claim_denied(self):
  self.receipt["physical_rtx_verified"]=True
  with self.assertRaisesRegex(ValueError,"false-green"):self.verify()
 def test_different_run_denied(self):
  self.receipt["run_id"]="0"*32
  with self.assertRaisesRegex(ValueError,"exact-run"):self.verify()
 def test_missing_import_denied(self):
  self.receipt["models"].pop()
  with self.assertRaisesRegex(ValueError,"five separate"):self.verify()
 def test_wrong_digest_denied(self):
  self.receipt["models"][2]["source_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"incomplete"):self.verify()
 def test_partial_clip_denied(self):
  self.receipt["models"][0]["animation_count"]=380
  with self.assertRaisesRegex(ValueError,"incomplete"):self.verify()
 def test_wrong_engine_denied(self):
  self.receipt["engine_version"]="Mock renderer"
  with self.assertRaisesRegex(ValueError,"Unreal version"):self.verify()

if __name__=="__main__":unittest.main()
