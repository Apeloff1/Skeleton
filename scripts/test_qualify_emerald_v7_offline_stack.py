"""Fail-closed offline qualifier tests: no original GLBs mocked into sign-off."""
from __future__ import annotations
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import qualify_emerald_v7_offline_stack as stack

class OfflineV7QualificationTests(unittest.TestCase):
 def setUp(self):
  root=tempfile.TemporaryDirectory()
  self.addCleanup(root.cleanup)
  self.root=Path(root.name)
  self.parts=[
   ({"offset":0,"bytes":4,"path":"parts/one","sha256":hashlib.sha256(b'abcd').hexdigest()},b'abcd'),
   ({"offset":4,"bytes":3,"path":"parts/two","sha256":hashlib.sha256(b'efg').hexdigest()},b'efg'),
  ]
  self.fake={"asset":"pathfinder.glb","bytes":7,
             "sha256":hashlib.sha256(b'abcdefg').hexdigest()}

 def test_one_exact_private_model_reassembled_from_source_parts(self):
  dest=self.root/"pathfinder.glb"
  with patch.object(stack.transport,"verified_zip",return_value=iter(self.parts)):
   result=stack.stage_v7_original(self.root/"not-an-actual-zip",self.fake,dest)
  self.assertEqual(dest.read_bytes(),b'abcdefg')
  self.assertEqual(result["model_bytes"],7)
  self.assertTrue(result["v7_original_bytes_verified"])

 def test_corrupt_or_reordered_raw_chunk_never_published(self):
  dest=self.root/"pathfinder.glb"
  forged=[({**self.parts[0][0],"offset":2},self.parts[0][1]),self.parts[1]]
  with patch.object(stack.transport,"verified_zip",return_value=iter(forged)):
   with self.assertRaisesRegex(ValueError,"part order"):
    stack.stage_v7_original(self.root/"fake.zip",self.fake,dest)
  self.assertFalse(dest.exists())

 def test_wrong_whole_model_sha_causes_cleanup(self):
  dest=self.root/"pathfinder.glb"
  altered={**self.fake,"sha256":"0"*64}
  with patch.object(stack.transport,"verified_zip",return_value=iter(self.parts)):
   with self.assertRaisesRegex(ValueError,"model reconstruction"):
    stack.stage_v7_original(self.root/"fake.zip",altered,dest)
  self.assertFalse(dest.exists())

 def test_existing_original_binary_is_never_overwritten(self):
  dest=self.root/"pathfinder.glb"
  dest.write_bytes(b"retain")
  with self.assertRaisesRegex(ValueError,"unused destination"):
   stack.stage_v7_original(self.root/"fake.zip",self.fake,dest)
  self.assertEqual(dest.read_bytes(),b"retain")

 def test_wrong_v6_exact_source_denied(self):
  (self.root/"pathfinder.glb").write_bytes(b"not the original")
  with self.assertRaisesRegex(ValueError,"missing exact original"):
   stack.verified_original_v6(self.root,"pathfinder")

 def test_invalid_resume_workspace_denied(self):
  with self.assertRaisesRegex(ValueError,"cannot resume"):
   stack.workspace_admission(self.root/"missing",True)
  dir=self.root/"work"
  stack.workspace_admission(dir,False)
  with self.assertRaisesRegex(ValueError,"fresh unique"):
   stack.workspace_admission(dir,False)
  with self.assertRaisesRegex(ValueError,"cannot resume"):
   stack.workspace_admission(dir,True)

 def test_forged_source_tool_receipt_denied(self):
  tools=self.root/"reviewed"
  tools.mkdir()
  (tools/"source-custody.json").write_text(json.dumps({
   "schema":"skeleton.emerald.reviewed-tools-custody.v1",
   "donor_sha256":stack.tools.MODEL_SHA,
   "staged_file_count":5,"source_executed_by_this_command":True,
   "original_model_bytes_copied":False,
   "measured_contact_clearance":False,"continuous_collision_qualified":False,
   "real_three_mixer_qualified":False,"artist_approved":False,
   "physical_rtx_verified":False,"release_qualified":False,
  }))
  with self.assertRaisesRegex(ValueError,"receipt differs"):
   stack.verify_staged_tools(tools)

 def test_incomplete_report_cannot_create_completion_receipt(self):
  invalid={"schema":"skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1",
           "stage":"pathfinder","sampled_screen_complete":False,"generation":"v7"}
  with self.assertRaisesRegex(ValueError,"incomplete"):
   stack.validate_operator_report(invalid,"pathfinder",self.fake)

 def test_false_hardware_flags_never_become_qualification(self):
  self.assertEqual(stack.SCHEMA,"skeleton.emerald.v7.offline-full-chain.v1")
  self.assertEqual(stack.STAGES,("pathfinder","archivist"))
  self.assertEqual(stack.SAMPLES_PER_STAGE,54)
  self.assertEqual(len(stack.tools.FILES),5)

 def test_dry_synthetic_conveyor_receipt_keeps_all_approval_holds(self):
  # This is deliberately a mocked source-contract test, NOT a substitute
  # for actual original GLB replay. It tests orchestration and receipt flags.
  wd=self.root/"work"
  forms=[
    {"stage":name,"asset":name+".glb",
     "bytes":7,"sha256":self.fake["sha256"],
     "zip_filename":name+".zip"}
    for name in stack.STAGES
  ]
  ledger={"forms":[{"stage":name,"full_report_sha256":"0"*64}
                   for name in stack.STAGES]}
  def stage_model(bundle,form,dest):
   Path(dest).write_bytes(b"abcdefg")
   return {"sha256":self.fake["sha256"]}
  def screen_report(stage,*_args,**_kwargs):
   return {"schema":"skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1",
           "stage":stage,"generation":"v7",
           "sampled_screen_complete":True,
           "total_sampled_blends":54,
           "observed_new_contact_instances":0,
           "samples":[{"within_8mm_not_contact":(415154 if stage=="pathfinder" else 0) if i==0 else 0}
                      for i in range(54)]}
  def validate(r,stage,form):
   return {"stage":stage,"sampled_poses":54,
           "new_contacts":0,
           "near_margin_pairs":sum(x["within_8mm_not_contact"] for x in r["samples"]),
           "continuous_collision_qualified":False}
  structural={"schema":"test.synthetic.only",
     "original_embedded_binary_prefix_exact":True,
     "original_mesh_skin_materials_exact":True,
     "growth_clip_exact":True,"modified_sampler_streams":1,
     "modified_keyframes":160}
  with patch.object(stack,"require_inputs",return_value=(
         forms,{name:self.root/(name+".v6") for name in stack.STAGES},
         {"contact":self.root/"dummy.zip","seams":self.root/"dummy2.zip"})),\
       patch.object(stack,"load_ledger",return_value=ledger),\
       patch.object(stack.tools,"stage",return_value={}),\
       patch.object(stack,"verify_staged_tools",return_value=True),\
       patch.object(stack,"stage_v7_original",side_effect=stage_model),\
       patch.object(stack.independent,"verify",return_value=structural),\
       patch.object(stack.screen,"run",side_effect=screen_report),\
       patch.object(stack,"validate_operator_report",side_effect=validate):
   result=stack.execute(wd,self.root,self.root,self.root/"c.zip",self.root/"s.zip",
                        resume=False,budget=60)
  self.assertEqual(result["actual_sampled_poses_replayed"],108)
  self.assertEqual(result["original_v7_glbs_verified"],2)
  self.assertTrue((wd/"qualification-complete.json").exists())
  for flag in ("continuous_collision_qualified","real_three_mixer_qualified",
               "artist_approved","physical_rtx_verified",
               "remote_binary_publication_verified","release_qualified"):
   self.assertFalse(result[flag],flag)

if __name__=="__main__":unittest.main()
