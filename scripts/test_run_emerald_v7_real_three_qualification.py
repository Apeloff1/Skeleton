"""Hostile operator replay orchestration fixtures, never original GLB evidence."""
from __future__ import annotations
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_emerald_v7_real_three_qualification as work

class V7ActualExecutionOperatorTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory()
  self.addCleanup(tmp.cleanup)
  self.root=Path(tmp.name)
  self.models=self.root/"models"
  self.tools=self.root/"original-reviewed-sources"
  self.models.mkdir()
  self.tools.mkdir()
  self.output=self.root/"result"
  self.fake={}
  for stage in work.STAGES:
   source=self.models/(stage+".glb")
   payload=("SYNTHETIC-NOT-AN-ORIGINAL-"+stage).encode()
   source.write_bytes(payload)
   self.fake[stage]=(len(payload),hashlib.sha256(payload).hexdigest())
  self.identity={
   "models":{
    stage:{"path":str(self.models/(stage+".glb")),
           "bytes":work.traces.PINS[stage][0],
           "sha256":work.traces.PINS[stage][1]}
    for stage in work.STAGES},
   "tools":str(self.tools),
   "node_executable":"node",
   "node_version":"v24.11.0",
   "three_version":"0.186.1",
   "source_sha256":{"synthetic_source":"0"*64},
   "three_runtime_sha256":{"synthetic_three":"1"*64},
  }

 def patched_execution(self,contacts=0,source_consistent=True,modify_stage=None):
  self.calls=[]
  def operator(stage,model,tool,root,node,budget):
   self.calls.append(stage)
   if modify_stage==stage:
    (self.models/(stage+".glb")).write_bytes(b"changed after SHA check")
   return {
     "stage":stage,
     "sampled_poses":54,
     "source_region_pair_types":3,
     "actual_three_mixer_process_executed":True,
     "source_pose_parity_process_executed":True,
     "reviewed_triangle_process_executed":True,
     "new_independent_contact_occurrences":contacts,
     "uncleared_near_margin_occurrences":100,
     "uncleared_attachment_seam_occurrences":551,
     "full_continuous_collision_qualified":False,
     "physical_rtx_verified":False,
     "release_qualified":False,
   }
  def paired(_models,_traces,_contacts,path):
   Path(path).write_text(json.dumps({
       "schema":"test.synthetic.source-report-consistency-only",
       "sampled_evolution_family_admitted":not source_consistent}))
   return {"sampled_evolution_family_admitted":not source_consistent,
           "sampled_three_pose_count":108,
           "reported_sampled_source_no_new_contacts":contacts==0}
  return (
   patch.object(work,"source_admission",return_value=self.identity),
   patch.dict(work.traces.PINS,self.fake,clear=True),
   patch.object(work,"operate_one",side_effect=operator),
   patch.object(work.consistency,"admit",side_effect=paired),
   patch.object(work,"source_hashes",side_effect=lambda mapping:
       self.identity["source_sha256"] if mapping is work.SOURCE_FILES
       else self.identity["three_runtime_sha256"]),
   patch.object(work.geometry,"sha",side_effect=lambda path:
       work.geometry.TOOLS[Path(path).name]),
  )

 def execute_mocked(self,**kwargs):
  ctx=self.patched_execution(**kwargs)
  for p in ctx:p.start()
  try:return work.execute(self.models,self.tools,self.output,budget=60)
  finally:
   for p in reversed(ctx):p.stop()

 def test_actual_execution_gate_still_preserves_all_independent_holds(self):
  result=self.execute_mocked()
  self.assertEqual(self.calls,["pathfinder","archivist"])
  self.assertEqual(result["sampled_three_mixer_poses_executed"],108)
  self.assertTrue(result["source_operator_sampled_only_qualified"])
  for key in ("original_model_auto_adopted","all_anatomical_pairs_qualified",
              "arbitrary_browser_loop_playheads_qualified",
              "continuous_collision_qualified",
              "browser_webgl_device_tested","artist_approved",
              "unreal_compiled","physical_rtx_verified",
              "remote_original_git_publication_verified",
              "independent_runtime_binary_signature_attested",
              "release_qualified"):
   self.assertFalse(result[key],key)
  self.assertTrue((self.output/"sampled-execution-receipt.json").exists())
  self.assertTrue((self.output/"source-report-consistency.json").exists())
  self.assertFalse((self.root/".result.three-pair.lock").exists())

 def test_partial_one_stage_source_fail_refuses_sampled_receipt(self):
  patches=self.patched_execution()
  def fail_second(stage,*_a):
   self.calls.append(stage)
   if stage=="archivist":raise ValueError("source geometry budget expired")
   return {"stage":stage,"sampled_poses":54,
           "actual_three_mixer_process_executed":True,
           "source_pose_parity_process_executed":True,
           "reviewed_triangle_process_executed":True}
  patches=list(patches)
  patches[2]=patch.object(work,"operate_one",side_effect=fail_second)
  for p in patches:p.start()
  try:
   with self.assertRaisesRegex(ValueError,"budget expired"):
    work.execute(self.models,self.tools,self.output,budget=60)
  finally:
   for p in reversed(patches):p.stop()
  self.assertFalse(self.output.exists())

 def test_runtime_script_modified_during_source_replay_aborts_publication(self):
  patches=list(self.patched_execution())
  observed=[0]
  def mutate_source(mapping):
   if mapping is work.SOURCE_FILES:
    observed[0]+=1
    if observed[0]>=1:
     return {"synthetic_source":"f"*64}
    return self.identity["source_sha256"]
   return self.identity["three_runtime_sha256"]
  patches[4]=patch.object(work,"source_hashes",side_effect=mutate_source)
  for p in patches:p.start()
  try:
   with self.assertRaisesRegex(ValueError,"source changed during operator"):
    work.execute(self.models,self.tools,self.output,budget=60)
  finally:
   for p in reversed(patches):p.stop()
  self.assertFalse(self.output.exists())

 def test_missing_parity_subprocess_prevents_source_admission(self):
  patches=list(self.patched_execution())
  def wrong_parity(stage,model,tool,root,node,budget):
   return {"stage":stage,"sampled_poses":54,
           "actual_three_mixer_process_executed":True,
           "source_pose_parity_process_executed":False,
           "reviewed_triangle_process_executed":True}
  patches[2]=patch.object(work,"operate_one",side_effect=wrong_parity)
  for p in patches:p.start()
  try:
   with self.assertRaisesRegex(ValueError,"missing actual original V7 mixer"):
    work.execute(self.models,self.tools,self.output,budget=60)
  finally:
   for p in reversed(patches):p.stop()
  self.assertFalse(self.output.exists())

 def test_static_json_report_flag_cannot_grant_positive_replay(self):
  with self.assertRaisesRegex(ValueError,"consistency gate changed"):
   self.execute_mocked(source_consistent=False)
  self.assertFalse(self.output.exists())

 def test_current_original_model_rehash_required_after_execution(self):
  with self.assertRaisesRegex(ValueError,"changed during operator"):
   self.execute_mocked(modify_stage="archivist")
  self.assertFalse(self.output.exists())

 def test_empty_or_existing_destination_is_not_overwritten(self):
  self.output.mkdir()
  (self.output/"keep").write_bytes(b"unchanged")
  with self.assertRaisesRegex(ValueError,"unused external"):
   work.source_admission(self.models,self.tools,self.output,"node")
  self.assertEqual((self.output/"keep").read_bytes(),b"unchanged")

 def test_operator_budget_cannot_be_unbounded(self):
  with self.assertRaisesRegex(ValueError,"runtime budget"):
   work.execute(self.models,self.tools,self.output,budget=float("inf"))
  with self.assertRaisesRegex(ValueError,"runtime budget"):
   work.execute(self.models,self.tools,self.output,budget=0)

 def test_source_glb_rejects_synthetic_model_before_any_child_process(self):
  with self.assertRaisesRegex(ValueError,"exact original V7 GLB"):
   work.source_admission(self.models,self.tools,self.output,"node")

 def test_python_node_and_shell_injection_variables_are_removed(self):
  with patch.dict(work.os.environ,{
    "PYTHONPATH":"/evil","NODE_OPTIONS":"--require=malware",
    "GITHUB_TOKEN":"secret","GH_TOKEN":"secret",
    "LD_PRELOAD":"/malware","HTTPS_PROXY":"https://evil",
    "PATH":"/usr/bin","HOME":"/tmp",
  }):
   env=work.sanitize_env()
  for key in ("PYTHONPATH","NODE_OPTIONS","GITHUB_TOKEN","GH_TOKEN",
              "LD_PRELOAD","HTTPS_PROXY"):
   self.assertNotIn(key,env)
  self.assertEqual(env["PYTHONNOUSERSITE"],"1")

 def test_subprocess_does_not_shell_expand_arguments_or_accept_nonzero_exit(self):
  class Complete:
   stdout=b"synthetic"
   stderr=b"failure"
   returncode=2
  with patch.object(work.subprocess,"run",return_value=Complete()) as running:
   with self.assertRaisesRegex(ValueError,"code 2"):
    work.closed_subprocess(["node","--version"],self.root,15)
   arguments=running.call_args
   self.assertEqual(arguments.args[0],["node","--version"])
   self.assertNotIn("shell",arguments.kwargs)
   self.assertEqual(arguments.kwargs["timeout"],15)

 def test_flooding_subprocess_logs_are_bounded_on_disk(self):
  class Complete:
   returncode=0
  def noisy(args,**kwargs):
   kwargs["stdout"].write(b"discarded-"+b"A"*(1024*1024)+b"last-stdout")
   kwargs["stderr"].write(b"discarded-"+b"B"*(1024*1024)+b"last-stderr")
   return Complete()
  with patch.object(work.subprocess,"run",side_effect=noisy) as invoked:
   receipt=work.closed_subprocess(["node","--version"],self.root,15)
  self.assertEqual(receipt["exit_code"],0)
  self.assertTrue(receipt["stdout_tail"].endswith("last-stdout"))
  self.assertTrue(receipt["stderr_tail"].endswith("last-stderr"))
  self.assertLessEqual(len(receipt["stdout_tail"]),400)
  self.assertLessEqual(len(receipt["stderr_tail"]),400)
  self.assertNotEqual(invoked.call_args.kwargs["stdout"],work.subprocess.PIPE)
  self.assertNotEqual(invoked.call_args.kwargs["stderr"],work.subprocess.PIPE)

 def test_failed_original_operator_escrows_only_incomplete_json_not_models(self):
  scratch=self.root/"scratch"
  (scratch/"traces").mkdir(parents=True)
  (scratch/"contacts").mkdir(parents=True)
  (scratch/"traces/pathfinder-three-mixer.json").write_text('{"stage":"pathfinder"}')
  (scratch/"contacts/pathfinder-contact-progress.json").write_text('{"incomplete":true}')
  (scratch/"pathfinder.glb").write_bytes(b"NEVER COPY MODEL")
  incomplete=self.root/"incident-escrow"
  payload=work.escrow_failed_source_evidence(
      scratch,incomplete,self.identity,ValueError("source budget expired"))
  self.assertEqual(payload["schema"],
                   "skeleton.emerald.v7.incomplete-original-mixer-incident.v1")
  self.assertEqual(len(payload["artifacts"]),2)
  self.assertTrue((incomplete/"INCOMPLETE-DO-NOT-ADOPT.json").exists())
  self.assertFalse((incomplete/"pathfinder.glb").exists())
  self.assertFalse(payload["release_qualified"])
  self.assertFalse(payload["sampled_evolution_family_admitted"])
  self.assertTrue(payload["complete_source_pose_count_unverified"])
  self.assertEqual(
      (incomplete/"traces/pathfinder-three-mixer.json").read_bytes(),
      (scratch/"traces/pathfinder-three-mixer.json").read_bytes())
  self.assertEqual(payload["artifacts"][0]["sha256"],
      hashlib.sha256(b'{"incomplete":true}').hexdigest())

 def test_incomplete_evidence_destination_cannot_be_overwritten(self):
  scratch=self.root/"scratch"
  scratch.mkdir()
  receipt=self.root/"already"
  receipt.mkdir()
  (receipt/"kept").write_bytes(b"preserve")
  with self.assertRaisesRegex(ValueError,"trusted unused"):
   work.escrow_failed_source_evidence(
        scratch,receipt,self.identity,RuntimeError("failure"))
  self.assertEqual((receipt/"kept").read_bytes(),b"preserve")

 def test_symlinked_incomplete_source_is_rejected(self):
  scratch=self.root/"scratch"
  (scratch/"traces").mkdir(parents=True)
  victim=self.root/"elsewhere.json"
  victim.write_bytes(b"unsafe referenced evidence")
  link=scratch/"traces/pathfinder-three-mixer.json"
  try:link.symlink_to(victim)
  except OSError:self.skipTest("symlinks not available")
  with self.assertRaisesRegex(ValueError,"unsafe or oversized"):
   work.escrow_failed_source_evidence(
        scratch,self.root/"quarantine",self.identity,
        RuntimeError("missing original stage"))
  self.assertFalse((self.root/"quarantine").exists())

 def test_partial_stage_failure_produces_incomplete_only_escrow(self):
  patches=list(self.patched_execution())
  def fail_after_pathfinder(stage,model,tools,workspace,node,budget):
   if stage=="archivist":
    raise ValueError("archivist genuine contact scan failed")
   (Path(workspace)/"traces"/"pathfinder-three-mixer.json").write_bytes(b'{"partial":true}')
   (Path(workspace)/"contacts"/"pathfinder-contact-progress.json").write_bytes(b'{"complete":false}')
   return {"stage":stage,"sampled_poses":54,
           "actual_three_mixer_process_executed":True,
           "source_pose_parity_process_executed":True,
           "reviewed_triangle_process_executed":True}
  patches[2]=patch.object(work,"operate_one",side_effect=fail_after_pathfinder)
  for source_patch in patches:source_patch.start()
  try:
   incident=self.root/"incomplete-incident"
   with self.assertRaisesRegex(ValueError,"archivist genuine"):
    work.execute(self.models,self.tools,self.output,
                 budget=60,failure_evidence=incident)
  finally:
   for source_patch in reversed(patches):source_patch.stop()
  self.assertFalse(self.output.exists())
  self.assertTrue((incident/"INCOMPLETE-DO-NOT-ADOPT.json").exists())
  self.assertFalse((incident/"sampled-execution-receipt.json").exists())
  self.assertTrue((incident/"traces/pathfinder-three-mixer.json").exists())
  summary=json.loads((incident/"INCOMPLETE-DO-NOT-ADOPT.json").read_bytes())
  self.assertFalse(summary["sampled_evolution_family_admitted"])
  self.assertFalse(summary["release_qualified"])
  self.assertFalse((self.root/".result.three-pair.lock").exists())

 def test_completed_operator_does_not_generate_incomplete_escrow(self):
  patches=list(self.patched_execution())
  for source_patch in patches:source_patch.start()
  incident=self.root/"should-remain-unused"
  try:
   result=work.execute(self.models,self.tools,self.output,
                       budget=60,failure_evidence=incident)
  finally:
   for source_patch in reversed(patches):source_patch.stop()
  self.assertEqual(result["sampled_three_mixer_poses_executed"],108)
  self.assertTrue(self.output.exists())
  self.assertFalse(incident.exists())

 def test_commit_source_artifacts_are_pinned_by_shas_in_receipt(self):
  self.assertTrue(work.NODE.name.endswith(".mjs"))
  self.assertTrue(work.PYTHON_CONTACT.name.endswith(".py"))
  self.assertEqual(work.STAGES,("pathfinder","archivist"))
  self.assertEqual(work.SCHEMA,"skeleton.emerald.v7.operated-three-and-triangles.sampled-only.v1")

if __name__=="__main__":
 unittest.main()
