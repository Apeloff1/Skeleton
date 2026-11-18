"""Hostile original V7 glTF scene/palette source tests; no fake model acceptance."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_emerald_v7_scene_palette as scene

def valid_synthetic_doc():
 """Tiny structural fixture: NOT an exact original GLB, ZIP or Three trace."""
 clips=[]
 for name,expected in scene.TRACKS.items():
  channels=[];samplers=[]
  for prop in ("rotation","translation"):
   for idx in range(expected[prop]):
    # The exact source uses a correction on palette joint 34 in orbit02.
    joint=scene.SKIN_PALETTE[idx]
    sampler=len(samplers)
    samplers.append({"input":0,"output":0,"interpolation":"LINEAR"})
    channels.append({"sampler":sampler,"target":{"node":joint,"path":prop}})
  clips.append({"name":name,"channels":channels,"samplers":samplers})
 for i in range(375):
  clips.append({"name":"reserved-synthetic-%03d"%i,
                "channels":[],"samplers":[]})
 clips.append({"name":"growth-pathfinder-to-archivist",
               "channels":[],"samplers":[]})
 nodes=[{"name":"source-joint-%03d"%i} for i in range(109)]
 nodes[0]={"name":"root","children":[1]}
 nodes[92]={"name":scene.MESH_NAME,"mesh":0,"skin":0}
 return {
  "asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":[0,92]}],
  "nodes":nodes,"meshes":[{"primitives":[]}],
  "skins":[{"skeleton":0,"inverseBindMatrices":0,
            "joints":list(scene.SKIN_PALETTE)}],
  "animations":clips,
  "accessors":[{"type":"VEC4","count":160,"componentType":5126}],
  "extras":{"stage":"pathfinder","donorSha256":scene.DONOR,
   "orbit02ClearanceCorrection":{
    "schema":"skeleton.emerald.orbit02-tail-clearance.v1",
    "joint_index":34,"clip":"orbit-02",
    "local_y_radians":.18,"modified_keyframes":160,
    "continuous_collision_qualified":False,
    "real_mixer_qualified":False,"artist_approved":False,
    "physical_rtx_verified":False,"release_qualified":False}},
 }

class V7ExactSceneTests(unittest.TestCase):
 def setUp(self):
  self.record=json.loads(scene.RECEIPT.read_bytes())
  self.source=valid_synthetic_doc()

 def test_recorded_two_original_complete_models_have_verified_sha_census(self):
  verified=scene.check_record(self.record)
  self.assertEqual(verified["checked_in_original_model_pins"],2)
  self.assertTrue(verified["recorded_source_scene_census_valid"])
  self.assertFalse(verified["actual_zip_bytes_replayed_in_this_source_only_step"])
  self.assertFalse(verified["release_qualified"])

 def test_reviewed_glb_scene_is_root_zero_and_mesh_node_92(self):
  result=scene.census(self.source,"pathfinder")
  self.assertEqual(result["scene_nodes"],[0,92])
  self.assertEqual(result["root_joint_name"],"root")
  self.assertEqual(result["joint_palette_after_mesh"],[88,89,90,91,93,94,95,96])
  self.assertEqual(result["animation_clip_count"],381)
  self.assertEqual(result["orbit02_corrected_rotation_keys"],160)
  self.assertFalse(result["real_three_mixer_qualified"])

 def test_mesh_skin_attachment_cannot_be_a_bone(self):
  invalid=copy.deepcopy(self.source)
  invalid["skins"][0]["joints"][92]=92
  with self.assertRaisesRegex(ValueError,"noncontiguous"):
   scene.census(invalid,"pathfinder")

 def test_scene_root_and_mesh_identity_cannot_be_swapped(self):
  for mutation in (
      lambda d:d["scenes"][0].update(nodes=[92,0]),
      lambda d:d["nodes"][0].update(name=scene.MESH_NAME),
      lambda d:d["nodes"][92].update(name="root"),
      lambda d:d["nodes"][92].update(skin=1),
      lambda d:d["nodes"][92].update(translation=[0.,0.,1.]),
  ):
   invalid=copy.deepcopy(self.source)
   mutation(invalid)
   with self.assertRaises(ValueError):scene.census(invalid,"pathfinder")

 def test_unapproved_joint_scale_is_rejected(self):
  self.source["nodes"][34]["scale"]=[1.1,1.,1.]
  with self.assertRaisesRegex(ValueError,"scaling"):
   scene.census(self.source,"pathfinder")

 def test_orbit02_original_tail_stream_required(self):
  clip=next(c for c in self.source["animations"] if c["name"]=="orbit-02")
  target=next(c for c in clip["channels"] if
              c["target"]=={"node":34,"path":"rotation"})
  clip["samplers"][target["sampler"]]["output"]=2
  with self.assertRaisesRegex(ValueError,"160-key"):
   scene.census(self.source,"pathfinder")

 def test_growth_target_and_381_clips_must_be_unchanged(self):
  self.source["animations"][-1]["name"]="growth-pathfinder-to-hoarder"
  with self.assertRaisesRegex(ValueError,"381-clip"):
   scene.census(self.source,"pathfinder")

 def test_wrong_translation_or_rotation_census_rejected(self):
  clip=next(c for c in self.source["animations"] if c["name"]=="orbit-02")
  clip["channels"][0]["target"]["path"]="translation"
  with self.assertRaisesRegex(ValueError,"duplicate|census"):
   scene.census(self.source,"pathfinder")

 def test_original_archive_zip_sha_and_model_sha_cannot_be_replaced(self):
  self.record["forms"][0]["zip_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"ZIP/GLB"):
   scene.check_record(self.record)
  self.record["forms"][0]["zip_sha256"]=scene.ZIP_PINS["pathfinder"][1]
  self.record["forms"][1]["glb_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"ZIP/GLB"):
   scene.check_record(self.record)

 def test_false_remote_publication_or_physical_approval_is_denied(self):
  for flag in ("original_git_remote_published",
               "live_browser_mixer_qualified",
               "continuous_collision_qualified",
               "artistic_approved","physical_rtx_verified",
               "release_qualified"):
   altered=copy.deepcopy(self.record);altered[flag]=True
   with self.assertRaisesRegex(ValueError,"falsely claims"):
    scene.check_record(altered)

 def test_missing_actual_original_zips_never_mark_replayed(self):
  with tempfile.TemporaryDirectory() as directory:
   with self.assertRaisesRegex(ValueError,"archive SHA or byte length"):
    scene.exact_archive(Path(directory),"pathfinder")

if __name__=="__main__":
 unittest.main()
