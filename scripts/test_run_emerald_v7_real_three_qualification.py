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
   "node_binary_sha256":"2"*64,
   "node_binary_bytes":120000,
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
   patch.object(work,"resolve_node_binary",return_value={
       "path":"node","sha256":"2"*64,"bytes":120000}),
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

 def test_subprocess_is_shell_free_and_refuses_nonzero_exit(self):
  command=[sys.executable,"-c",
           "import sys;print(sys.argv[1]);sys.exit(2)",
           "literal; echo SHOULD_NOT_EXECUTE"]
  with self.assertRaisesRegex(ValueError,"code 2"):
   work.closed_subprocess(command,self.root,15)

 def test_child_streams_are_bounded_in_ram(self):
  script=("import sys;"
          "sys.stdout.write('A'*1048576+'last-stdout');"
          "sys.stderr.write('B'*1048576+'last-stderr')")
  receipt=work.closed_subprocess([sys.executable,"-c",script],
                                  self.root,15)
  self.assertEqual(receipt["exit_code"],0)
  self.assertTrue(receipt["stdout_tail"].endswith("last-stdout"))
  self.assertTrue(receipt["stderr_tail"].endswith("last-stderr"))
  self.assertLessEqual(len(receipt["stdout_tail"]),400)
  self.assertLessEqual(len(receipt["stderr_tail"]),400)

 def test_child_over_output_quota_is_terminated(self):
  script=("import sys;sys.stdout.write('A'*1048576);sys.stdout.flush()")
  with patch.object(work,"MAX_CHILD_OUTPUT_BYTES",65536):
   with self.assertRaisesRegex(ValueError,"output quota exceeded"):
    work.closed_subprocess([sys.executable,"-c",script],
                           self.root,15)

 def test_child_timeout_is_terminated(self):
  script="import time;time.sleep(30)"
  with self.assertRaisesRegex(ValueError,"time limit exceeded"):
   work.closed_subprocess([sys.executable,"-c",script],
                          self.root,.05)

 def test_node_binary_is_sha_pinned_not_just_version_text(self):
  dummy=self.root/"node"
  dummy.write_bytes(b"#!/bin/sh\n"+b"#"*5000)
  dummy.chmod(0o755)
  receipt=work.resolve_node_binary(str(dummy))
  self.assertEqual(receipt["sha256"],hashlib.sha256(dummy.read_bytes()).hexdigest())
  self.assertEqual(receipt["bytes"],dummy.stat().st_size)
  dummy.chmod(0o644)
  with self.assertRaisesRegex(ValueError,"trusted executable"):
   work.resolve_node_binary(str(dummy))
  dummy.chmod(0o755)
  link=self.root/"linked-node"
  try:link.symlink_to(dummy)
  except OSError:self.skipTest("symlinks unavailable")
  with self.assertRaisesRegex(ValueError,"trusted executable"):
   work.resolve_node_binary(str(link))

 def test_node_binary_mutation_aborts_before_receipt_publication(self):
  patches=list(self.patched_execution())
  calls=[0]
  def mutated(_executable):
   calls[0]+=1
   return {"path":"node","sha256":"3"*64,"bytes":120000}
  patches[-1]=patch.object(work,"resolve_node_binary",side_effect=mutated)
  for p in patches:p.start()
  try:
   with self.assertRaisesRegex(ValueError,"Node runtime executable changed"):
    work.execute(self.models,self.tools,self.output,budget=60)
  finally:
   for p in reversed(patches):p.stop()
  self.assertFalse(self.output.exists())

 def test_commit_source_artifacts_are_pinned_by_shas_in_receipt(self):
  self.assertTrue(work.NODE.name.endswith(".mjs"))
  self.assertTrue(work.PYTHON_CONTACT.name.endswith(".py"))
  self.assertEqual(work.STAGES,("pathfinder","archivist"))
  self.assertEqual(work.SCHEMA,"skeleton.emerald.v7.operated-three-and-triangles.sampled-only.v1")

if __name__=="__main__":
 unittest.main()
