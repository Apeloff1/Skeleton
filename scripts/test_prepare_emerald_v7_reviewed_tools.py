"""Hostile source archive tests, with independent exact production pin assertions."""
from __future__ import annotations
import copy,hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare_emerald_v7_reviewed_tools as reviewed

class OriginalContactSourceTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory()
  self.addCleanup(temp.cleanup)
  self.root=Path(temp.name)
  self.out=self.root/"qualified"
  self.data={
   "contact_audit.py":b"from __future__ import annotations\n# audit\n",
   "contact_geometry.py":b"# geometry\n",
   "contact_geometry_accel.py":b"# accelerated\n",
   "fast_wing_witness.py":b"# witness\n",
   "analyze_seams.py":b"# original seam\n",
  }
  self.pins={name:("seams" if name=="analyze_seams.py" else "contact",
                    len(data),hashlib.sha256(data).hexdigest())
             for name,data in self.data.items()}
  self.paths={kind:self.root/(kind+".zip") for kind in ("contact","seams")}
  self._refresh()
  spec={
   kind:{"name":path.name,"bytes":path.stat().st_size,
         "sha256":reviewed.digest(path)}
   for kind,path in self.paths.items()
  }
  pin=patch.dict(reviewed.ARCHIVES,spec,clear=True)
  pin.start();self.addCleanup(pin.stop)
  pinfiles=patch.dict(reviewed.FILES,self.pins,clear=True)
  pinfiles.start();self.addCleanup(pinfiles.stop)

 def _refresh(self,extras=None):
  extras=extras or {}
  for kind,path in self.paths.items():
   with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_STORED) as archive:
    for filename,(source_kind,_,_) in self.pins.items():
     if source_kind==kind:
      archive.writestr("Tools/"+filename,self.data[filename])
    for filename,data in extras.get(kind,{}).items():
     archive.writestr(filename,data)

 def _update_zip_pin(self,kind):
  path=self.paths[kind]
  reviewed.ARCHIVES[kind]={
   "name":path.name,"bytes":path.stat().st_size,
   "sha256":reviewed.digest(path),
  }

 def qualify(self):
  return reviewed.stage(self.paths["contact"],self.paths["seams"],self.out)

 def test_production_original_source_pins_are_reviewed(self):
  # Synthetic setup replaces runtime pins only inside this test instance.
  self.assertEqual(len(reviewed.FILES),5)
  self.assertEqual(set(reviewed.FILES),set(self.data))

 def test_exact_synthetic_stage_is_complete_and_never_qualifies_gpu(self):
  result=self.qualify()
  self.assertEqual(result["staged_file_count"],5)
  self.assertFalse(result["source_executed_by_this_command"])
  self.assertFalse(result["continuous_collision_qualified"])
  self.assertFalse(result["physical_rtx_verified"])
  self.assertFalse(result["release_qualified"])
  for file,data in self.data.items():
   self.assertEqual((self.out/file).read_bytes(),data)
  self.assertEqual(set(path.name for path in self.out.iterdir()),
                   set(self.data)|{"source-custody.json"})
  self.assertFalse((self.root/".qualified.qualification.lock").exists())

 def test_archive_modified_without_approval_rejected(self):
  self.paths["contact"].write_bytes(b"modified")
  with self.assertRaisesRegex(ValueError,"archive source"):
   self.qualify()
  self.assertFalse(self.out.exists())

 def test_reviewed_source_tool_modified_but_archive_reapproved_rejected(self):
  self.data["contact_geometry.py"]=b"altered but still importable\n"
  self._refresh()
  self._update_zip_pin("contact")
  with self.assertRaisesRegex(ValueError,"source tool length"):
   self.qualify()
  self.assertFalse(self.out.exists())

 def test_archive_traversal_member_rejected(self):
  self._refresh({"contact":{"../outside.txt":b"escape"}})
  self._update_zip_pin("contact")
  with self.assertRaisesRegex(ValueError,"unsafe, linked"):
   self.qualify()
  self.assertFalse((self.root/"outside.txt").exists())

 def test_duplicate_casefold_member_rejected(self):
  self._refresh({"contact":{"Tools/CONTACT_AUDIT.PY":b"wrong"}})
  self._update_zip_pin("contact")
  with self.assertRaisesRegex(ValueError,"unsafe, linked"):
   self.qualify()

 def test_existing_destination_never_overwritten(self):
  self.out.mkdir()
  (self.out/"kept").write_bytes(b"safe")
  with self.assertRaisesRegex(ValueError,"trusted unused"):
   self.qualify()
  self.assertEqual((self.out/"kept").read_bytes(),b"safe")

 def test_symlink_output_refused(self):
  victim=self.root/"victim"
  victim.mkdir()
  try:self.out.symlink_to(victim,target_is_directory=True)
  except OSError:self.skipTest("symlink unsupported")
  with self.assertRaisesRegex(ValueError,"trusted unused"):
   self.qualify()
  self.assertEqual(list(victim.iterdir()),[])

 def test_symlink_input_archive_refused(self):
  linked=self.root/"linked.zip"
  try:linked.symlink_to(self.paths["contact"])
  except OSError:self.skipTest("symlink unsupported")
  with self.assertRaisesRegex(ValueError,"archive source"):
   reviewed.stage(linked,self.paths["seams"],self.out)

 def test_replay_never_overwrites_published_original_files(self):
  self.qualify()
  with self.assertRaisesRegex(ValueError,"trusted unused"):
   self.qualify()

 def test_lock_collision_refused(self):
  lock=self.root/".qualified.qualification.lock"
  lock.mkdir()
  with self.assertRaisesRegex(ValueError,"already publishing"):
   self.qualify()
  self.assertTrue(lock.exists())

if __name__=="__main__":unittest.main()
