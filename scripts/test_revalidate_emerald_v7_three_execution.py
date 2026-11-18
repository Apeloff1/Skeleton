"""Synthetic adversarial validation of original V7 operator evidence custody.

Mocks are labeled and never constitute a real 229MB GLB/Three/triangle run.
The test checks that a self-asserted positive operator report cannot be
independently accepted without every corresponding byte and source receipt.
"""
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
import revalidate_emerald_v7_three_execution as verify

def digest(data):return hashlib.sha256(data).hexdigest()
def put(path,document):
 path=Path(path)
 raw=json.dumps(document,separators=(",",":")).encode()
 path.write_bytes(raw)
 return digest(raw)

class IndependentV7EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.context=tempfile.TemporaryDirectory()
  self.addCleanup(self.context.cleanup)
  self.base=Path(self.context.name)
  self.models=self.base/"models"
  self.tools=self.base/"original-tools"
  self.evidence=self.base/"executed-source-receipt"
  self.models.mkdir()
  self.tools.mkdir()
  self.evidence.mkdir()
  (self.evidence/"traces").mkdir()
  (self.evidence/"contacts").mkdir()
  self.pins={}
  for stage in verify.STAGES:
   model=("SYNTHETIC-ORIGINAL-SHA-TEST-"+stage).encode()
   (self.models/(stage+".glb")).write_bytes(model)
   self.pins[stage]=(len(model),digest(model))
  self.source_hash={"synthetic_operator_source":"a"*64}
  self.runtime_hash={"synthetic_three":"b"*64}
  self.tool_pins={}
  for name in verify.contact.TOOLS:
   data=("SYNTHETIC-ORIGINAL-TOOL-"+name).encode()
   (self.tools/name).write_bytes(data)
   self.tool_pins[name]=digest(data)
  put(self.tools/"source-custody.json",{"schema":"synthetic-only"})
  self.source_info=[]
  self.results=[]
  for index,stage in enumerate(verify.STAGES):
   trace_sha=put(self.evidence/"traces"/(stage+"-three-mixer.json"),{
       "schema":"synthetic-never-original","stage":stage})
   contact_sha=put(self.evidence/"contacts"/(stage+"-actual-three-contacts.json"),{
       "schema":"synthetic-never-original","stage":stage})
   put(self.evidence/"contacts"/(stage+"-contact-progress.json"),{
       "schema":"synthetic-never-original-progress","stage":stage})
   self.results.append({
       "stage":stage,
       "original_v7_model_sha256":self.pins[stage][1],
       "actual_three_source_trace_sha256":trace_sha,
       "reviewed_triangle_report_sha256":contact_sha,
       "actual_three_mixer_process_executed":True,
       "reviewed_triangle_process_executed":True,
       "sampled_poses":54,"source_region_pair_types":3,
       "new_independent_contact_occurrences":0,
       "uncleared_near_margin_occurrences":100,
       "uncleared_attachment_seam_occurrences":551,
       "independent_world_matrix_error_max":0.,
       "full_continuous_collision_qualified":False,
       "physical_rtx_verified":False,"release_qualified":False,
   })
   self.source_info.append({
       "stage":stage,
       "source_glb_sha256":self.pins[stage][1],
       "source_three_trace_sha256":trace_sha,
       "reviewed_contact_report_sha256":contact_sha,
       "new_independent_contact_occurrences":0,
       "original_three_poses_checked":54,
   })
  self.consistency={
    "schema":verify.paired.SCHEMA,
    "sampled_three_pose_count":108,
    "sampled_evolution_family_admitted":False,
    "reported_sampled_source_no_new_contacts":True,
    "original_donor_sha256":verify.traces.DONOR,
    "model_stages":list(verify.STAGES),
    "source_original_models_sha_rechecked":True,
    "release_qualified":False,"source_results":self.source_info,
  }
  consistent_sha=put(self.evidence/"source-report-consistency.json",
                     self.consistency)
  self.receipt={
    "schema":verify.operator.SCHEMA,
    "donor_sha256":verify.traces.DONOR,
    "original_stage_order":list(verify.STAGES),
    "original_model_count":2,
    "original_glb_byte_total":229515688,
    "real_three_package_version":"0.186.1",
    "node_runtime_version":"v24.11.0",
    "exact_model_sha_rechecked_before_and_after":True,
    "source_original_models_sha_rechecked":True,
    "sampled_three_mixer_poses_executed":108,
    "reviewed_anatomical_pair_types":3,
    "source_operator_executed_mixer":True,
    "source_operator_executed_triangle_contact":True,
    "source_operator_sampled_only_qualified":True,
    "source_geometry_hashes":self.tool_pins,
    "source_script_sha256":self.source_hash,
    "installed_three_runtime_file_sha256":self.runtime_hash,
    "original_three_binding_manifest_sha256":
        verify.digest(verify.operator.bindings.MANIFEST),
    "original_skin_and_clip_binding_results":{
        stage:{"stage":stage,"original_skin_joint_count":108,
               "original_glTF_node_count":109,
               "actual_mixer_clip_bindings_exact":True,
               "source_original_model_rechecked":True,
               "source_original_model_sha256":self.pins[stage][1],
               "release_qualified":False}
        for stage in verify.STAGES},
    "two_stage_consistency_receipt_sha256":consistent_sha,
    "stages":self.results,
  }
  self.receipt.update({flag:False for flag in verify.EXPLICIT_HOLDS})
  self.write_receipt()

 def write_receipt(self):
  put(self.evidence/"sampled-execution-receipt.json",self.receipt)

 def patched(self):
  reviewed={
    "original_three_poses_checked":54,
    "new_independent_contact_occurrences":0,
    "sampled_three_mixer_contacts_clear":True,
    "unqualified_8mm_near_margin_occurrences":100,
    "unqualified_inherited_attachment_seam_occurrences":551,
    "worst_independent_world_matrix_error":0.,
  }
  return [
    patch.dict(verify.traces.PINS,self.pins,clear=True),
    patch.dict(verify.contact.TOOLS,self.tool_pins,clear=True),
    patch.object(verify.operator,"source_hashes",side_effect=lambda mapping:
       self.source_hash if mapping is verify.operator.SOURCE_FILES
       else self.runtime_hash),
    patch.object(verify.traces,"verify",return_value={
       "full_model_sha_independently_rechecked":True,
       "sampled_poses":54}),
    patch.object(verify.paired,"verify_contact",return_value=reviewed),
  ]

 def qualify(self):
  patches=self.patched()
  for p in patches:p.start()
  try:return verify.validate(self.models,self.tools,self.evidence)
  finally:
   for p in reversed(patches):p.stop()

 def test_synthetic_evidence_consistency_never_attests_process_execution(self):
  output=self.qualify()
  self.assertEqual(output["original_model_count"],2)
  self.assertEqual(output["sampled_three_pose_consistency_checked"],108)
  self.assertTrue(output["sampled_source_report_consistent"])
  self.assertFalse(output["actual_mixer_and_geometry_reexecuted_by_this_validator"])
  self.assertFalse(output["independent_proof_of_process_execution"])
  self.assertFalse(output["continuous_collision_qualified"])
  self.assertFalse(output["release_qualified"])

 def test_changed_source_original_glb_denied(self):
  filename=self.models/"pathfinder.glb"
  data=bytearray(filename.read_bytes())
  data[0]^=1
  filename.write_bytes(data)
  with self.assertRaisesRegex(ValueError,"source model GLB SHA differs"):
   self.qualify()

 def test_mutated_three_trace_rejected_before_positive_consistency(self):
  path=self.evidence/"traces/pathfinder-three-mixer.json"
  path.write_bytes(path.read_bytes()+b"\n")
  with self.assertRaisesRegex(ValueError,"incomplete or forged"):
   self.qualify()

 def test_changed_contact_report_rejected_before_positive_consistency(self):
  path=self.evidence/"contacts/archivist-actual-three-contacts.json"
  path.write_bytes(path.read_bytes()+b"\n")
  with self.assertRaisesRegex(ValueError,"incomplete or forged"):
   self.qualify()

 def test_mismatched_two_stage_consistency_digest_denied(self):
  self.receipt["two_stage_consistency_receipt_sha256"]="f"*64
  self.write_receipt()
  with self.assertRaisesRegex(ValueError,"paired source-only"):
   self.qualify()

 def test_removed_original_model_rejected(self):
  (self.models/"archivist.glb").unlink()
  with self.assertRaisesRegex(ValueError,"evidence directory"):
   self.qualify()

 def test_wrong_or_missing_source_code_sha_denied(self):
  self.receipt["source_script_sha256"]={"synthetic_operator_source":"f"*64}
  self.write_receipt()
  with self.assertRaisesRegex(ValueError,"source bytes changed"):
   self.qualify()

 def test_missing_original_binding_preflight_denied(self):
  self.receipt["original_skin_and_clip_binding_results"].pop("archivist")
  self.write_receipt()
  with self.assertRaisesRegex(ValueError,"binding preflight"):
   self.qualify()

 def test_forged_browser_gpu_artist_and_release_denied(self):
  for flag in verify.EXPLICIT_HOLDS:
   altered=copy.deepcopy(self.receipt)
   altered[flag]=True
   put(self.evidence/"sampled-execution-receipt.json",altered)
   with self.assertRaisesRegex(ValueError,"release/device/continuous"):
    self.qualify()

 def test_absent_execution_status_denied(self):
  self.receipt["source_operator_executed_mixer"]=False
  self.write_receipt()
  with self.assertRaisesRegex(ValueError,"incomplete original source execution"):
   self.qualify()

 def test_unrecognized_file_or_symlinked_evidence_tree_denied(self):
  extra=self.evidence/"unsigned-contact.json"
  extra.write_bytes(b"{}")
  with self.assertRaisesRegex(ValueError,"evidence directory"):
   self.qualify()
  extra.unlink()
  link=self.evidence/"traces/pathfinder-three-mixer.json"
  link.unlink()
  try:link.symlink_to(self.evidence/"traces/archivist-three-mixer.json")
  except OSError:self.skipTest("symlink unavailable")
  with self.assertRaisesRegex(ValueError,"evidence directory"):
   self.qualify()

 def test_reviewed_original_geometry_tool_mutation_denied(self):
  file=self.tools/"contact_audit.py"
  file.write_bytes(file.read_bytes()+b"modified")
  with self.assertRaisesRegex(ValueError,"implementation SHA changed"):
   self.qualify()

 def test_source_model_and_pinned_receipt_codes_have_explicit_nonrelease_flags(self):
  self.assertEqual(verify.SCHEMA,
       "skeleton.emerald.v7.independent-receipt-revalidation.v1")
  self.assertEqual(verify.STAGES,("pathfinder","archivist"))
  self.assertEqual(verify.operator.THREE_VERSION,"0.186.1")
  self.assertTrue("physical_rtx_verified" in verify.EXPLICIT_HOLDS)

if __name__=="__main__":
 unittest.main()
