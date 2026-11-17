"""Synthetic glTF/ZIP contract regression. It is NOT physical original evidence."""
from __future__ import annotations
import copy,hashlib,json,math,struct,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_emerald_v7_original_zip_pair as audit

def make_glb(doc,data):
 js=json.dumps(doc,separators=(",",":"),ensure_ascii=False).encode()
 js+=b" "*((-len(js))%4)
 data+=b"\0"*((-len(data))%4)
 total=28+len(js)+len(data)
 return (struct.pack("<4sIIII",b"glTF",2,total,len(js),0x4e4f534a)
         +js+struct.pack("<II",len(data),0x004e4942)+data)

def fixture():
 stage="pathfinder";q=struct.pack("<4f",0,0,0,1)*160
 clip={"name":"orbit-02",
       "channels":[{"sampler":0,"target":{"node":34,"path":"rotation"}}],
       "samplers":[{"input":0,"output":0,"interpolation":"LINEAR"}]}
 clips=[clip]+[{"name":f"motion-{n:03}","samplers":[],"channels":[]}
               for n in range(379)]
 clips.append({"name":"growth-pathfinder-to-archivist",
               "samplers":[],"channels":[]})
 old={"asset":{"version":"2.0"},
      "extras":{"stage":stage,"donorSha256":audit.DONOR},
      "skins":[{"joints":list(range(108))}],
      "nodes":[],"meshes":[],"materials":[],
      "animations":clips,
      "buffers":[{"byteLength":len(q)}],
      "bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":len(q)}],
      "accessors":[{"bufferView":0,"type":"VEC4","componentType":5126,"count":160}]}
 new=copy.deepcopy(old)
 new["animations"][0]["samplers"][0]["output"]=1
 new["bufferViews"].append({"buffer":0,"byteOffset":2560,"byteLength":2560})
 new["accessors"].append({"bufferView":1,"type":"VEC4",
                          "componentType":5126,"count":160})
 new["buffers"][0]["byteLength"]=5120
 new["extras"]["orbit02ClearanceCorrection"]={
   "schema":"skeleton.emerald.orbit02-tail-clearance.v1",
   "source_v6_sha256":audit.FILES[stage]["v6"][1],
   "donor_sha256":audit.DONOR,
   "joint_index":34,"clip":"orbit-02","local_y_radians":.18,
   "modified_keyframes":160,"equipment_enabled":False,
   "continuous_collision_qualified":False,
   "real_mixer_qualified":False,"crossfade_transition_qualified":False,
   "artist_approved":False,"physical_rtx_verified":False,
   "release_qualified":False}
 s=math.sin(.09);c=math.cos(.09)
 added=struct.pack("<4f",0,s,0,c)*160
 return make_glb(old,q),make_glb(new,q+added),old,new,q,added

class ExactV7ZipAuditTests(unittest.TestCase):
 def test_pins_and_models_scope(self):
  self.assertEqual(audit.STAGES,("pathfinder","archivist"))
  self.assertEqual(audit.JOINT,34)
  self.assertEqual(audit.CLIP,"orbit-02")
  self.assertEqual(audit.ANGLE,.18)
  self.assertEqual(audit.FILES["pathfinder"]["v7"][0],114696520)
  self.assertEqual(audit.FILES["archivist"]["v7"][0],114819168)

 def test_exact_source_byte_prefix_and_one_rotation_accepted(self):
  a,b,*_=fixture()
  summary=audit.compare_old_new(a,b,"pathfinder")
  self.assertTrue(summary["original_binary_prefix_identical"])
  self.assertEqual(summary["new_animation_accessors"],1)
  self.assertEqual(summary["modified_keyframes"],160)
  self.assertFalse(summary["release_qualified"])

 def test_mutated_source_binary_prefix_is_rejected(self):
  _,b,old,new,q,extra=fixture()
  altered=bytearray(q);altered[0]=1
  with self.assertRaisesRegex(ValueError,"BIN bytes changed"):
   audit.compare_old_new(make_glb(old,bytes(altered)),b,"pathfinder")

 def test_nonauthorized_new_animation_is_denied(self):
  a,_,old,new,q,extra=fixture()
  new["animations"][1]["name"]="renamed-motion"
  with self.assertRaisesRegex(ValueError,"source animation declarations"):
   audit.compare_old_new(a,make_glb(new,q+extra),"pathfinder")

 def test_invalid_orbit02_correction_quaternion_denied(self):
  a,_,old,new,q,extra=fixture()
  corrupted=struct.pack("<4f",0,0,0,1)*160
  with self.assertRaisesRegex(ValueError,"not the reviewed"):
   audit.compare_old_new(a,make_glb(new,q+corrupted),"pathfinder")

 def test_fabricated_artist_and_release_flags_denied(self):
  a,_,old,new,q,extra=fixture()
  for key in ("real_mixer_qualified","physical_rtx_verified",
              "artist_approved","release_qualified"):
   altered=copy.deepcopy(new)
   altered["extras"]["orbit02ClearanceCorrection"][key]=True
   with self.assertRaisesRegex(ValueError,"false GPU"):
    audit.compare_old_new(a,make_glb(altered,q+extra),"pathfinder")

 def test_wrong_rig_joint_count_denied(self):
  a,_,old,new,q,extra=fixture()
  wrong=copy.deepcopy(new)
  wrong["skins"][0]["joints"].pop()
  with self.assertRaisesRegex(ValueError,"source rig"):
   audit.compare_old_new(a,make_glb(wrong,q+extra),"pathfinder")

 def test_bounded_unsafe_original_zip_member_denied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=root/"source.zip";dest=root/"out.glb"
   with zipfile.ZipFile(source,"w") as z:
    z.writestr("pathfinder.glb",b"abcd")
    z.writestr("../traversal",b"unsafe")
   sha=audit.digest(source)
   fake=(4,hashlib.sha256(b"abcd").hexdigest(),source.stat().st_size,sha)
   with patch.dict(audit.FILES,{"pathfinder":{"v6":fake}}):
    with self.assertRaisesRegex(ValueError,"untrusted original member"):
     audit.archive_to_scratch(source,"pathfinder","v6",dest)
   self.assertFalse(dest.exists())
   self.assertFalse((root/"traversal").exists())

 def test_original_zip_cannot_be_replaced_after_pin(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=root/"source.zip";dest=root/"out.glb"
   with zipfile.ZipFile(source,"w") as z:z.writestr("pathfinder.glb",b"abcd")
   sha=audit.digest(source)
   fake=(4,hashlib.sha256(b"abcd").hexdigest(),source.stat().st_size,sha)
   source.write_bytes(source.read_bytes()+b"unexpected")
   with patch.dict(audit.FILES,{"pathfinder":{"v6":fake}}):
    with self.assertRaisesRegex(ValueError,"archive byte custody"):
     audit.archive_to_scratch(source,"pathfinder","v6",dest)
   self.assertFalse(dest.exists())

 def test_existing_receipt_path_cannot_be_overwritten(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);dest=root/"receipt.json"
   dest.write_bytes(b"keep")
   with self.assertRaisesRegex(ValueError,"unused receipt"):
    audit.audit(root,root,dest)
   self.assertEqual(dest.read_bytes(),b"keep")

if __name__=="__main__":unittest.main()
