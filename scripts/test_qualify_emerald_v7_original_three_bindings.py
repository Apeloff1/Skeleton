"""Original V7 palette and target fingerprints: strict mocked-GLB negative tests.

Synthetic glTF bytes here are never a substitute for the two exact original
114–115MB models or live Three mixer execution. Tests patch pins only inside
the fixture, never change committed source-model or publication hashes.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import qualify_emerald_v7_original_three_bindings as census

def fixture(stage="pathfinder"):
 palette=list(range(92))+list(range(93,109))
 nodes=[{"name":"original_joint_"+str(i)} for i in range(109)]
 nodes[92]={"name":"source unskinned mesh node","mesh":0,"skin":0}
 animation_names=list(census.CLIPS)+[f"other-source-animation-{i:03}" for i in range(376)]
 accessors=[{"type":"SCALAR","componentType":5126,
             "min":[0.0],"max":[6.5],"count":2}]
 animations=[]
 for name in animation_names:
  if name in census.CLIPS:
   animations.append({
     "name":name,
     "samplers":[
       {"input":0,"output":0,"interpolation":"LINEAR"},
       {"input":0,"output":0,"interpolation":"LINEAR"}],
     "channels":[
       {"sampler":0,"target":{"node":1,"path":"translation"}},
       {"sampler":1,"target":{"node":34,"path":"rotation"}}],
   })
  else:animations.append({"name":name,"samplers":[],"channels":[]})
 return {
  "asset":{"version":"2.0"},
  "extras":{"stage":stage,"donorSha256":census.DONOR},
  "nodes":nodes,"skins":[{"joints":palette}],
  "animations":animations,"accessors":accessors,
 }

def fake_glb(document):
 packed=json.dumps(document,separators=(",",":")).encode("utf-8")
 packed+=b" "*((-len(packed))%4)
 payload=b"\x01\x02\x03\x04"
 output=bytearray(28+len(packed)+len(payload))
 struct.pack_into("<4sIIII",output,0,b"glTF",2,len(output),len(packed),0x4e4f534a)
 output[20:20+len(packed)]=packed
 struct.pack_into("<II",output,20+len(packed),len(payload),0x004e4942)
 output[28+len(packed):]=payload
 return bytes(output)

class V7OriginalSkinBindingTests(unittest.TestCase):
 def setUp(self):
  self.manifest=census.manifest()
  self.document=fixture()
  self.descriptor=census.describe(self.document,"pathfinder")

 def test_both_real_source_model_pins_and_all_five_actual_clip_fingerprints(self):
  self.assertEqual([x["stage"] for x in self.manifest["models"]],
                   ["pathfinder","archivist"])
  self.assertEqual(self.manifest["skin_joint_count"],108)
  self.assertEqual(self.manifest["node_count"],109)
  self.assertEqual(self.manifest["mesh_node_index"],92)
  self.assertEqual(self.manifest["skin_palette_json_sha256"],census.EXACT_PALETTE_SHA)
  self.assertEqual([x["channels"] for x in self.manifest["clips"]],
                   [114,124,88,88,123])
  self.assertEqual([x["rotation"] for x in self.manifest["clips"]],
                   [97,106,71,71,105])
  self.assertEqual([x["translation"] for x in self.manifest["clips"]],
                   [17,18,17,17,18])
  self.assertEqual(self.manifest["models"][0]["model_bytes"],114696520)
  self.assertEqual(self.manifest["models"][1]["model_bytes"],114819168)
  self.assertFalse(self.manifest["release_qualified"])

 def test_synthetic_source_palette_has_original_noncontiguous_108_order(self):
  self.assertEqual(self.descriptor["skin_joint_count"],108)
  self.assertEqual(self.descriptor["node_count"],109)
  self.assertEqual(self.descriptor["last_corrective_joint_node_index"],108)
  self.assertEqual(self.descriptor["skin_palette_json_sha256"],census.EXACT_PALETTE_SHA)
  self.assertEqual(len(self.descriptor["clips"]),5)
  ledger=copy.deepcopy(self.manifest)
  ledger["clips"]=self.descriptor["clips"]
  self.assertTrue(census.compare_descriptor(self.descriptor,ledger)
                  ["actual_mixer_clip_bindings_exact"])

 def test_swapped_mesh_node_or_renumbered_corrective_joint_denied(self):
  altered=copy.deepcopy(self.document)
  altered["skins"][0]["joints"].remove(108)
  altered["skins"][0]["joints"].append(92)
  with self.assertRaisesRegex(ValueError,"original skin palette"):
   census.describe(altered,"pathfinder")
  altered=copy.deepcopy(self.document)
  altered["nodes"][92].pop("skin")
  with self.assertRaisesRegex(ValueError,"original skin palette"):
   census.describe(altered,"pathfinder")

 def test_wrong_source_stage_or_donor_denied(self):
  for key,value in (("stage","archivist"),("donorSha256","0"*64)):
   altered=copy.deepcopy(self.document)
   altered["extras"][key]=value
   with self.assertRaisesRegex(ValueError,"stage or donor"):
    census.describe(altered,"pathfinder")

 def test_invalid_target_or_duplicate_track_denied(self):
  altered=copy.deepcopy(self.document)
  altered["animations"][0]["channels"][0]["target"]["node"]=92
  with self.assertRaisesRegex(ValueError,"mesh or interpolation"):
   census.describe(altered,"pathfinder")
  altered=copy.deepcopy(self.document)
  altered["animations"][0]["channels"][1]["target"]={"node":1,"path":"translation"}
  with self.assertRaisesRegex(ValueError,"duplicate source joint"):
   census.describe(altered,"pathfinder")

 def test_changed_clip_target_hash_or_duration_never_approved(self):
  ledger=copy.deepcopy(self.manifest)
  ledger["clips"]=copy.deepcopy(self.descriptor["clips"])
  ledger["clips"][0]["targets_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"target SHA"):
   census.compare_descriptor(self.descriptor,ledger)
  ledger["clips"]=copy.deepcopy(self.descriptor["clips"])
  ledger["clips"][0]["duration_seconds"]=7.2
  with self.assertRaisesRegex(ValueError,"target SHA"):
   census.compare_descriptor(self.descriptor,ledger)

 def test_extra_clip_or_nonmonotonic_timebase_metadata_denied(self):
  altered=copy.deepcopy(self.document)
  altered["animations"][0]["samplers"][0]["interpolation"]="STEP"
  with self.assertRaisesRegex(ValueError,"mesh or interpolation"):
   census.describe(altered,"pathfinder")
  altered=copy.deepcopy(self.document)
  altered["accessors"][0]["min"]=[1]
  with self.assertRaisesRegex(ValueError,"motion timebase"):
   census.describe(altered,"pathfinder")
  altered=copy.deepcopy(self.document)
  altered["animations"].pop()
  with self.assertRaisesRegex(ValueError,"clip count"):
   census.describe(altered,"pathfinder")

 def test_forged_artistic_qualification_or_release_manifest_denied(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/"receipt.json"
   for flag in ("joint_or_clip_retarget_approved",
                "real_mixer_original_run_completed",
                "full_continuous_collision_qualified","artist_approved",
                "physical_rtx_verified","release_qualified"):
    changed=copy.deepcopy(self.manifest)
    changed[flag]=True
    path.write_text(json.dumps(changed))
    with self.assertRaisesRegex(ValueError,"falsely elevated"):
     census.manifest(path)

 def test_exact_model_read_uses_full_file_hash_not_a_json_only_approximation(self):
  with tempfile.TemporaryDirectory() as directory:
   original=Path(directory)/"pathfinder.glb"
   original.write_bytes(fake_glb(self.document))
   size=original.stat().st_size
   digest=census.sha(original.read_bytes())
   ledger=copy.deepcopy(self.manifest)
   ledger["clips"]=copy.deepcopy(self.descriptor["clips"])
   with patch.dict(census.OUTPUTS,
                   {"pathfinder":(size,digest)},clear=False):
    result=census.inspect_model(original,"pathfinder",ledger)
    self.assertTrue(result["source_original_model_rechecked"])
    self.assertTrue(result["actual_mixer_clip_bindings_exact"])
    self.assertFalse(result["release_qualified"])
    bad=bytearray(original.read_bytes())
    bad[-1]^=1
    original.write_bytes(bad)
    with self.assertRaisesRegex(ValueError,"SHA-256 or inode"):
     census.inspect_model(original,"pathfinder",ledger)

if __name__=="__main__":
 unittest.main()
