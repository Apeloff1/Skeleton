"""Fail-closed synthetic V5 proximal publication and sampled evidence tests."""
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_emerald_v5_proximal_publication as pub

class ProximalCustodyTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  self.root=Path(tmp.name);self.parts=self.root/"parts";self.parts.mkdir()
  raw=[b"original-left",b"original-right"]
  self.fixture={"stage":"pathfinder","model":"pathfinder.glb",
   "sha256":hashlib.sha256(b"".join(raw)).hexdigest(),
   "bytes":sum(map(len,raw)),
   "parts":[]}
  for i,data in enumerate(raw):
   name="pathfinder.glb.part"+str(i+1).zfill(3)
   (self.parts/name).write_bytes(data)
   self.fixture["parts"].append({"path":"assets/emerald/evolution-v5/pathfinder/"+name,
    "offset":sum(map(len,raw[:i])),"bytes":len(data),
    "sha256":hashlib.sha256(data).hexdigest()})

 def test_real_manifest_stays_unqualified(self):
  forms,raw=pub.load()
  self.assertEqual(len(forms),2)
  self.assertEqual(sum(x["bytes"] for x in forms),229498312)
  self.assertEqual(sum(len(x["parts"]) for x in forms),8)
  self.assertTrue(all(x["release_qualified"] is False and
     x["full_continuous_collision_qualified"] is False for x in forms))

 def test_synthetic_exact_assembly(self):
  output=self.root/"pathfinder.glb"
  r=pub.assemble(self.parts,output,self.fixture)
  self.assertTrue(r["assembled"])
  self.assertFalse(r["release_qualified"])
  self.assertEqual(output.read_bytes(),b"original-leftoriginal-right")

 def test_wrong_whole_digest_refuses_publication(self):
  self.fixture["sha256"]="0"*64
  output=self.root/"pathfinder.glb"
  with self.assertRaisesRegex(ValueError,"assembled output"):
   pub.assemble(self.parts,output,self.fixture)
  self.assertFalse(output.exists())

 def test_corrupt_part_denied_before_write(self):
  (self.parts/"pathfinder.glb.part001").write_bytes(b"tampered")
  output=self.root/"pathfinder.glb"
  with self.assertRaisesRegex(ValueError,"slice"):
   pub.assemble(self.parts,output,self.fixture)
  self.assertFalse(output.exists())

 def test_existing_output_untouched(self):
  output=self.root/"pathfinder.glb";output.write_bytes(b"keep")
  with self.assertRaisesRegex(ValueError,"trusted new"):
   pub.assemble(self.parts,output,self.fixture)
  self.assertEqual(output.read_bytes(),b"keep")

 def test_missing_git_blob_denied(self):
  with self.assertRaisesRegex(ValueError,"remote Git blob"):
   pub.verify_tree(self.root,self.fixture)

 def test_unauthorized_origin_denied(self):
  with patch.object(pub,"git",return_value=b"https://invalid.invalid/surveillance\\n"):
   with self.assertRaisesRegex(ValueError,"origin"):
    pub.publish(self.root,self.fixture,self.parts,b"irrelevant")

 def test_receipts_do_not_confer_continuous_clearance(self):
  p=pub.ROOT/"assets/emerald/evolution-v5/proximal-wingfold-qualification.json"
  r=json.loads(p.read_bytes())
  self.assertEqual(len(r["forms"]),2)
  for item in r["forms"]:
   self.assertEqual(len(item["samples"]),7)
   self.assertTrue(all(x["contacts"]==0 and x["near_pairs"]==0 for x in item["samples"]))
   self.assertEqual(item["unclassified_triangles"],449393)
   self.assertLess(item["p95_strain_delta"],.003)
   self.assertFalse(item["continuous_collision_qualified"])

if __name__=="__main__":unittest.main()
