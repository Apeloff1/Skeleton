"""Synthetic remote Git custody fixtures, never original GLB qualification."""
from __future__ import annotations
import copy,hashlib,json,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_emerald_v7_remote_original as remote
import publish_emerald_v7_orbit02 as transport

def model(stage="pathfinder"):
 doc={
  "asset":{"version":"2.0"},
  "skins":[{"joints":list(range(108))}],
  "animations":[{"name":f"clip-{i:03}"} for i in range(381)],
  "extras":{
   "stage":stage,
   "donorSha256":remote.DONOR,
   "orbit02ClearanceCorrection":{
    "schema":"skeleton.emerald.orbit02-tail-clearance.v1",
    "source_v6_sha256":transport.SOURCES[stage][1],
    "donor_sha256":remote.DONOR,
    "joint_index":34,"clip":"orbit-02",
    "local_y_radians":.18,
    "modified_sampler_streams":1,"modified_keyframes":160,
    "equipment_enabled":False,
    "continuous_collision_qualified":False,
    "real_mixer_qualified":False,
    "crossfade_transition_qualified":False,
    "artist_approved":False,
    "unreal_compiled":False,
    "physical_rtx_verified":False,"release_qualified":False,
   },
  },
 }
 data=b"\x01\x02\x03\x04"
 doc["buffers"]=[{"byteLength":len(data)}]
 js=json.dumps(doc,separators=(",",":")).encode()
 js+=b" "*((-len(js))%4)
 total=28+len(js)+len(data)
 return struct.pack("<4sIIII",b"glTF",2,total,len(js),0x4e4f534a)+js+struct.pack("<II",len(data),0x004e4942)+data

def fixture():
 original=model()
 pivot=len(original)//2
 chunks=[original[:pivot],original[pivot:]]
 entry=[]
 for i,chunk in enumerate(chunks):
  entry.append({
    "path":f"assets/emerald/evolution-v7/pathfinder/pathfinder.glb.part{i+1:03}",
    "bytes":len(chunk),"sha256":transport.digest(chunk),
    "offset":sum(len(c) for c in chunks[:i]),
  })
 form={"stage":"pathfinder","asset":"pathfinder.glb",
       "bytes":len(original),"sha256":transport.digest(original),
       "source_v6_sha256":transport.SOURCES["pathfinder"][1],
       "automatic_adoption":False,
       "continuous_collision_qualified":False,"real_three_mixer_qualified":False,
       "artistic_approved":False,"physical_rtx_verified":False,
       "release_qualified":False,"parts":entry}
 return form,chunks

class OriginalRemoteGitTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory()
  self.addCleanup(temp.cleanup)
  self.root=Path(temp.name)
  self.form,self.chunks=fixture()

 def test_exact_checked_out_glb_parse(self):
  path=self.root/"pathfinder.glb"
  path.write_bytes(b"".join(self.chunks))
  details=remote.verify_model_shape(path,self.form)
  self.assertEqual(details["rig_joints"],108)
  self.assertEqual(details["corrected_quaternion_keys"],160)
  self.assertFalse(details["release_qualified"])

 def test_wrong_original_glb_source_sha_denied(self):
  path=self.root/"pathfinder.glb"
  data=bytearray(b"".join(self.chunks))
  data[-1]^=1
  path.write_bytes(data)
  with self.assertRaisesRegex(ValueError,"fully assembled"):
   remote.verify_model_shape(path,self.form)

 def test_no_false_original_glb_metadata_acceptance(self):
  path=self.root/"pathfinder.glb"
  with patch.object(remote.transport,"sha",return_value=self.form["sha256"]):
   data=b"".join(self.chunks)
   # This fixture declares the actual original length even under a mocked SHA.
   with patch.object(Path,"stat",wraps=path.stat) if False else patch.object(remote.transport,"sha",return_value=self.form["sha256"]):
    path.write_bytes(data)
    form=copy.deepcopy(self.form)
    form["source_v6_sha256"]="0"*64
    with self.assertRaisesRegex(ValueError,"does not match source-bound"):
     remote.verify_model_shape(path,form)

 def test_exact_remote_blob_mode_and_sha(self):
  entry=self.form["parts"][0]
  data=self.chunks[0]
  oid="a"*40
  text=f"100644 blob {oid}\t{entry['path']}\n".encode()
  def git(_root,*cmd):
   if cmd[0]=="ls-tree":return text
   if cmd[:2]==("cat-file","-t"):return b"blob\n"
   if cmd[:2]==("cat-file","-s"):return str(len(data)).encode()
   if cmd[:2]==("cat-file","blob"):return data
   raise AssertionError(cmd)
  with patch.object(transport,"git",side_effect=git):
   payload,result=remote.remote_part(self.root,"b"*40,entry)
  self.assertEqual(payload,data)
  self.assertEqual(result,oid)

 def test_lfs_pointer_and_nonblob_tree_entries_denied(self):
  entry=self.form["parts"][0]
  for mode in ("120000","160000","100755"):
   text=f"{mode} blob {'a'*40}\t{entry['path']}\n".encode()
   with patch.object(transport,"git",return_value=text):
    with self.assertRaisesRegex(ValueError,"ordinary raw blob"):
     remote.remote_part(self.root,"b"*40,entry)
  with patch.object(transport,"git",return_value=b""):
   with self.assertRaisesRegex(ValueError,"missing"):
    remote.remote_part(self.root,"b"*40,entry)

 def test_same_size_mutated_remote_blob_denied(self):
  entry=self.form["parts"][0]
  data=b"X"*len(self.chunks[0])
  oid="a"*40
  text=f"100644 blob {oid}\t{entry['path']}\n".encode()
  def git(_root,*cmd):
   if cmd[0]=="ls-tree":return text
   if cmd[:2]==("cat-file","-t"):return b"blob\n"
   if cmd[:2]==("cat-file","-s"):return str(len(data)).encode()
   if cmd[:2]==("cat-file","blob"):return data
   raise AssertionError(cmd)
  with patch.object(transport,"git",side_effect=git):
   with self.assertRaisesRegex(ValueError,"wrong SHA-256"):
    remote.remote_part(self.root,"b"*40,entry)

 def test_assembled_model_requires_all_exact_git_parts(self):
  out=self.root/"pathfinder.glb"
  calls=iter(zip(self.chunks,["a"*40,"b"*40]))
  with patch.object(remote,"remote_part",side_effect=lambda *_:next(calls)):
   result=remote.stream_form(self.root,"c"*40,self.form,out)
  self.assertEqual(result["verified_raw_git_parts"][0]["sha256"],
                   self.form["parts"][0]["sha256"])
  self.assertEqual(out.read_bytes(),b"".join(self.chunks))
  self.assertEqual(result["model_sha256"],self.form["sha256"])

 def test_reordered_or_truncated_part_rolls_back_partial_output(self):
  out=self.root/"pathfinder.glb"
  bad=copy.deepcopy(self.form)
  bad["parts"][1]["offset"]+=1
  calls=iter(zip(self.chunks,["a"*40,"b"*40]))
  with patch.object(remote,"remote_part",side_effect=lambda *_:next(calls)):
   with self.assertRaisesRegex(ValueError,"contiguous"):
    remote.stream_form(self.root,"c"*40,bad,out)
  self.assertFalse(out.exists())

 def test_untrusted_destination_never_overwritten(self):
  out=self.root/"pathfinder.glb"
  out.write_bytes(b"precious")
  with self.assertRaisesRegex(ValueError,"new original"):
   remote.stream_form(self.root,"c"*40,self.form,out)
  self.assertEqual(out.read_bytes(),b"precious")

 def test_remote_concurrent_ref_mutation_denied(self):
  with patch.object(transport,"head",return_value=("refs/heads/assets/test","a"*40)),\
       patch.object(transport,"git",return_value=(("b"*40)+" refs/heads/assets/test\n").encode()):
   with self.assertRaisesRegex(ValueError,"moved after fetch"):
    remote.remote_revision(self.root,self.form,b"manifest")

 def test_remote_incomplete_publication_never_generates_complete_receipt(self):
  self.assertEqual(remote.RECEIPT_SCHEMA,
                   "skeleton.emerald.v7.git-original-remote-reassembly.v1")
  with patch.object(transport,"authorized",return_value=None),\
       patch.object(transport,"load",return_value=([self.form],b"manifest")):
   with self.assertRaisesRegex(ValueError,"incomplete original"):
    remote.verify_remote(self.root,self.root/"out")
  self.assertFalse((self.root/"out").exists())

if __name__=="__main__":unittest.main()
