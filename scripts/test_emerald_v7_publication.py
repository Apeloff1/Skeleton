"""Synthetic V7 raw binary negative-path tests, never substitute for the 229 MB assets."""
from __future__ import annotations
import hashlib,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import publish_emerald_v7_orbit02 as custody

class V7BinaryCustodyTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory()
  self.addCleanup(tmp.cleanup)
  self.root=Path(tmp.name)
  data=b"actual-candidate-not-a-placeholder"
  self.payload=data
  self.form={
   "stage":"pathfinder","asset":"pathfinder.glb",
   "bytes":len(data),"sha256":custody.digest(data),
   "parts":[
    {"path":"assets/emerald/evolution-v7/pathfinder/pathfinder.glb.part001",
     "offset":0,"bytes":12,"sha256":custody.digest(data[:12])},
    {"path":"assets/emerald/evolution-v7/pathfinder/pathfinder.glb.part002",
     "offset":12,"bytes":len(data)-12,"sha256":custody.digest(data[12:])},
   ],
  }

 def archive(self,alter=None,extra=None):
  location=self.root/"payload.zip"
  with zipfile.ZipFile(location,"w") as z:
   z.writestr("pathfinder.glb",self.payload if alter is None else alter)
   if extra is not None:z.writestr(extra,b"hostile file")
  self.form["zip_sha256"]=custody.sha(location)
  return location

 def test_pinned_real_publication_manifest_is_not_a_release(self):
  forms,raw=custody.load()
  self.assertEqual([f["stage"] for f in forms],["pathfinder","archivist"])
  self.assertEqual(sum(f["bytes"] for f in forms),229515688)
  self.assertEqual(sum(len(f["parts"]) for f in forms),8)
  self.assertTrue(all(f["release_qualified"] is False
                 and f["automatic_adoption"] is False for f in forms))

 def test_synthetic_verified_zip_extraction_never_changes_bytes(self):
  rows=list(custody.verified_zip(self.archive(),self.form))
  self.assertEqual(b"".join(chunk for _,chunk in rows),self.payload)
  self.assertEqual(len(rows),2)

 def test_same_length_corrupted_binary_rejected(self):
  altered=self.payload[:-1]+b"X"
  with self.assertRaisesRegex(ValueError,"chunk SHA mismatch"):
   list(custody.verified_zip(self.archive(alter=alter),self.form))

 def test_original_container_digest_fails_closed(self):
  bundle=self.archive()
  self.form["zip_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"unverified original ZIP"):
   list(custody.verified_zip(bundle,self.form))

 def test_zip_traversal_rejected(self):
  with self.assertRaisesRegex(ValueError,"ZIP member"):
   list(custody.verified_zip(self.archive(extra="../evil"),self.form))

 def test_duplicate_casefold_member_denied(self):
  p=self.root/"duplicate.zip"
  with zipfile.ZipFile(p,"w") as z:
   z.writestr("pathfinder.glb",self.payload)
   z.writestr("PATHFINDER.GLB",b"duplicate")
  self.form["zip_sha256"]=custody.sha(p)
  with self.assertRaisesRegex(ValueError,"ZIP member"):
   list(custody.verified_zip(p,self.form))

 def test_real_local_byte_parts_required(self):
  with self.assertRaisesRegex(ValueError,"missing"):
   custody.verify_tree(self.root,self.form)
  for part in self.form["parts"]:
   p=self.root/part["path"]
   p.parent.mkdir(parents=True,exist_ok=True)
   p.write_bytes(self.payload[part["offset"]:part["offset"]+part["bytes"]])
  verified=custody.verify_tree(self.root,self.form)
  self.assertTrue(verified["actual_git_bytes_verified"])
  self.assertFalse(verified["release_qualified"])

 def test_changed_same_length_git_slice_denied(self):
  for part in self.form["parts"]:
   path=self.root/part["path"];path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(self.payload[part["offset"]:part["offset"]+part["bytes"]])
  bad=self.root/self.form["parts"][1]["path"]
  bad.write_bytes(b"X"*bad.stat().st_size)
  with self.assertRaisesRegex(ValueError,"raw Git blob altered"):
   custody.verify_tree(self.root,self.form)

 def test_unauthorized_origin_cannot_publish(self):
  with patch.object(custody,"git",return_value=b"ssh://attacker.invalid/repository.git\n"):
   with self.assertRaisesRegex(ValueError,"unauthorized original"):
    custody.authorized(self.root)

 def test_no_historical_hoarder_publication(self):
  with self.assertRaisesRegex(ValueError,"unsupported published"):
   custody.target_ref("hoarder")

 def test_git_object_sha_validation(self):
  for value in (b"",b"0"*39,b"0"*65,b"not-a-commit"):
   with self.assertRaisesRegex(ValueError,"untrusted Git object"):
    custody.oid(value)

if __name__=="__main__":unittest.main()
