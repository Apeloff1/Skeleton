"""V6 binary transport hostile fixtures, no actual giant model in CI."""
import hashlib,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch

import publish_emerald_v6_tail as pub

class PublicationContractTests(unittest.TestCase):
 def setUp(self):
  folder=tempfile.TemporaryDirectory()
  self.addCleanup(folder.cleanup)
  self.root=Path(folder.name)
  self.data=b"ORIGINAL-DRAGON-PAYLOAD"
  self.form={
   "stage":"pathfinder","asset":"pathfinder.glb",
   "bytes":len(self.data),"sha256":pub.digest(self.data),
   "parts":[
    {"path":"assets/emerald/evolution-v6/pathfinder/pathfinder.glb.part001",
     "offset":0,"bytes":8,"sha256":pub.digest(self.data[:8])},
    {"path":"assets/emerald/evolution-v6/pathfinder/pathfinder.glb.part002",
     "offset":8,"bytes":len(self.data)-8,"sha256":pub.digest(self.data[8:])},
   ],
  }

 def bundle(self,blob=None,extra=None):
  path=self.root/"original.zip"
  with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as z:
   z.writestr("pathfinder.glb",self.data if blob is None else blob)
   if extra is not None:z.writestr(extra,b"unsafe")
  return path

 def test_original_full_manifest_cannot_claim_publication(self):
  forms,raw=pub.load()
  self.assertEqual(len(forms),2)
  self.assertEqual(sum(f["bytes"] for f in forms),229508900)
  self.assertEqual(sum(len(f["parts"]) for f in forms),8)
  self.assertTrue(all(f["release_qualified"] is False and
       f["cross_clip_transition_qualified"] is False for f in forms))

 def test_exact_original_member_verified_without_extraction(self):
  result=list(pub.verified_archive(self.bundle(),self.form))
  self.assertEqual(len(result),2)
  self.assertEqual(b"".join(data for _,data in result),self.data)

 def test_tampered_same_length_original_rejected(self):
  with self.assertRaisesRegex(ValueError,"chunk hash mismatch"):
   list(pub.verified_archive(self.bundle(blob=self.data[:-1]+b"X"),self.form))

 def test_unsafe_path_members_rejected(self):
  with self.assertRaisesRegex(ValueError,"unsafe ZIP"):
   list(pub.verified_archive(self.bundle(extra="../escapes.bin"),self.form))

 def test_duplicate_casefold_names_rejected(self):
  path=self.root/"duplicates.zip"
  with zipfile.ZipFile(path,"w") as z:
   z.writestr("pathfinder.glb",self.data)
   z.writestr("PATHFINDER.GLB",b"x")
  with self.assertRaisesRegex(ValueError,"unsafe ZIP"):
   list(pub.verified_archive(path,self.form))

 def test_absent_git_chunk_rejected(self):
  with self.assertRaisesRegex(ValueError,"missing Git"):
   pub.verify_tree(self.root,self.form)

 def test_actual_original_parts_can_be_independently_reassembled(self):
  for row in self.form["parts"]:
   path=self.root/row["path"]
   path.parent.mkdir(parents=True,exist_ok=True)
   data=self.data[row["offset"]:row["offset"]+row["bytes"]]
   path.write_bytes(data)
  result=pub.verify_tree(self.root,self.form)
  self.assertTrue(result["actual_checkout_bytes_verified"])
  self.assertFalse(result["release_qualified"])

 def test_refuse_tampered_original_git_part(self):
  for row in self.form["parts"]:
   path=self.root/row["path"]
   path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(self.data[row["offset"]:row["offset"]+row["bytes"]])
  (self.root/self.form["parts"][1]["path"]).write_bytes(b"x"*self.form["parts"][1]["bytes"])
  with self.assertRaisesRegex(ValueError,"changed"):
   pub.verify_tree(self.root,self.form)

 def test_unauthorized_git_remote_denied(self):
  with patch.object(pub,"git",return_value=b"ssh://evil.invalid/repo.git\n"):
   with self.assertRaisesRegex(ValueError,"authorized Skeleton"):
    pub.check_remote(self.root)

 def test_unknown_publication_target_denied(self):
  with self.assertRaises(ValueError):
   pub.branch("hoarder")

 def test_empty_or_wrong_git_oid_denied(self):
  for value in (b"",b"f"*39,b"0"*65,b"not-a-sha"):
   with self.assertRaisesRegex(ValueError,"invalid Git"):
    pub.oid(value)

if __name__=="__main__":
 unittest.main()
