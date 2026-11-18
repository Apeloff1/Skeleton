"""Read-only second-pass validation of an executed two-V7 Three/triangle receipt.

No model adoption, merge, release, physical GPU, live-browser claims, or
subprocess execution. This reconstructs evidence identity and checks that all
stored pose/contact counts reconcile to the two exact original models. A
separate operator run remains necessary to produce actual execution evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

import admit_emerald_v7_three_mixer_pair as paired
import check_emerald_v7_three_mixer_trace as traces
import emerald_v6_crossfade_screen as contact
import run_emerald_v7_real_three_qualification as operator

SCHEMA="skeleton.emerald.v7.independent-receipt-revalidation.v1"
STAGES=("pathfinder","archivist")
MAX_ROOT=512*1024
MAX_CONSISTENCY=512*1024
MAX_TRACE=traces.MAX_REPORT_BYTES
MAX_CONTACT=paired.CONTACT_BUDGET
MAX_SOURCE_ROOT=4
EXPLICIT_HOLDS=(
 "original_model_auto_adopted","all_anatomical_pairs_qualified",
 "arbitrary_browser_loop_playheads_qualified","continuous_collision_qualified",
 "browser_webgl_device_tested","artist_approved","unreal_compiled",
 "physical_rtx_verified","remote_original_git_publication_verified",
 "independent_runtime_binary_signature_attested","release_qualified",
)

def require(value,message):
 if not value:raise ValueError(message)

def digest(path):
 path=Path(path)
 flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)
 with os.fdopen(os.open(path,flags),"rb") as stream:
  prior=os.fstat(stream.fileno())
  require(stat.S_ISREG(prior.st_mode),"original evidence not a regular file")
  result=hashlib.file_digest(stream,"sha256").hexdigest()
  after=os.fstat(stream.fileno())
  require((prior.st_dev,prior.st_ino,prior.st_size,prior.st_mtime_ns,prior.st_ctime_ns)==
          (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
          "evidence mutated during source verification")
  return result

def bounded_json(path,maximum):
 path=Path(path)
 require(path.is_file() and not path.is_symlink()
         and 0<path.stat().st_size<=maximum,
         "missing, linked or oversized original V7 evidence")
 flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)
 with os.fdopen(os.open(path,flags),"rb") as stream:
  prior=os.fstat(stream.fileno())
  require(stat.S_ISREG(prior.st_mode) and
          0<prior.st_size<=maximum,"evidence changed on open")
  content=stream.read(maximum+1)
  after=os.fstat(stream.fileno())
  require(0<len(content)==prior.st_size<=maximum and
          (prior.st_dev,prior.st_ino,prior.st_mtime_ns,prior.st_ctime_ns)==
          (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns),
          "altered or unbounded evidence read")
  return json.loads(content),hashlib.sha256(content).hexdigest()

def exact_directory(root,expected):
 root=Path(root)
 require(root.is_dir() and not root.is_symlink() and
         {x.name for x in root.iterdir()}==set(expected) and
         all(not x.is_symlink() for x in root.iterdir()),
         "original source evidence directory is incomplete, linked or unexpected")

def source_identity(record):
 require(record.get("schema")==operator.SCHEMA
         and record.get("donor_sha256")==traces.DONOR
         and record.get("original_stage_order")==list(STAGES)
         and record.get("original_model_count")==2
         and record.get("original_glb_byte_total")==229515688
         and record.get("real_three_package_version")=="0.186.1"
         and isinstance(record.get("node_runtime_version"),str)
         and re.fullmatch(r"v24\.\d+\.\d+",record["node_runtime_version"])
         and record.get("exact_model_sha_rechecked_before_and_after") is True
         and record.get("sampled_three_mixer_poses_executed")==108
         and record.get("reviewed_anatomical_pair_types")==3
         and record.get("source_operator_executed_mixer") is True
         and record.get("source_operator_executed_triangle_contact") is True
         and record.get("source_operator_sampled_only_qualified") is True
         and record.get("source_original_models_sha_rechecked",True) is True,
         "incomplete original source execution claims or changed source family")
 require(all(record.get(flag) is False for flag in EXPLICIT_HOLDS),
         "positive release/device/continuous collision flag is forbidden")
 require(record.get("source_geometry_hashes")==contact.TOOLS,
         "reviewed source contact toolchain changed")
 require(record.get("source_script_sha256")==operator.source_hashes(operator.SOURCE_FILES)
         and record.get("installed_three_runtime_file_sha256")==
             operator.source_hashes(operator.THREE_RUNTIME_FILES),
         "original mixer/operator or installed Three runtime source bytes changed")
 require(record.get("original_three_binding_manifest_sha256")==
             digest(operator.bindings.MANIFEST),
         "original source animation binding fingerprint manifest changed")
 bindings=record.get("original_skin_and_clip_binding_results")
 require(isinstance(bindings,dict) and set(bindings)==set(STAGES),
         "missing original Three glTF skin binding preflight")
 for stage in STAGES:
  b=bindings[stage]
  require(b.get("stage")==stage and
          b.get("original_skin_joint_count")==108 and
          b.get("original_glTF_node_count")==109 and
          b.get("actual_mixer_clip_bindings_exact") is True and
          b.get("source_original_model_rechecked") is True and
          b.get("source_original_model_sha256")==traces.PINS[stage][1] and
          b.get("release_qualified") is False,
          "original glTF palette or source clip binding preflight differs")
 return True

def check_stage(stage,receipt,trace,trace_sha,triangle,triangle_sha,model):
 pins=traces.PINS[stage]
 require(receipt.get("stage")==stage and
         receipt.get("original_v7_model_sha256")==pins[1] and
         receipt.get("actual_three_source_trace_sha256")==trace_sha and
         receipt.get("reviewed_triangle_report_sha256")==triangle_sha and
         receipt.get("actual_three_mixer_process_executed") is True and
         receipt.get("reviewed_triangle_process_executed") is True and
         receipt.get("sampled_poses")==54 and
         receipt.get("source_region_pair_types")==3 and
         all(receipt.get(flag) is False for flag in (
             "full_continuous_collision_qualified","physical_rtx_verified","release_qualified")),
         "incomplete or forged original two-stage execution receipt")
 trace_report=traces.verify(trace,stage,model)
 require(trace_report["full_model_sha_independently_rechecked"] is True
         and trace_report["sampled_poses"]==54,
         "actual original Three trace does not match its full original model")
 reviewed=paired.verify_contact(triangle,stage,trace,trace_sha)
 require(reviewed["original_three_poses_checked"]==54
         and reviewed["new_independent_contact_occurrences"]==0
         and reviewed["sampled_three_mixer_contacts_clear"] is True,
         "unqualified original Three triangle contact report")
 require(receipt.get("new_independent_contact_occurrences")==0 and
         receipt.get("uncleared_near_margin_occurrences")==
             reviewed["unqualified_8mm_near_margin_occurrences"] and
         receipt.get("uncleared_attachment_seam_occurrences")==
             reviewed["unqualified_inherited_attachment_seam_occurrences"] and
         type(receipt.get("independent_world_matrix_error_max")) in (int,float) and
         math.isfinite(receipt["independent_world_matrix_error_max"]) and
         abs(receipt["independent_world_matrix_error_max"]-
             reviewed["worst_independent_world_matrix_error"])<=1e-12,
         "saved original contact witness summary was suppressed or changed")
 return {
  "stage":stage,"original_model_sha256":pins[1],
  "original_model_bytes":pins[0],
  "actual_three_trace_sha256":trace_sha,
  "reviewed_triangle_report_sha256":triangle_sha,
  "sampled_three_poses_consistency_checked":54,
  "reported_independent_new_contacts":0,
  "uncleared_near_margin_occurrences":
      reviewed["unqualified_8mm_near_margin_occurrences"],
  "uncleared_attachment_seam_occurrences":
      reviewed["unqualified_inherited_attachment_seam_occurrences"],
  "raw_original_model_sha_rechecked":True,
  "source_three_animation_reexecuted_by_this_validator":False,
  "source_triangle_geometry_reexecuted_by_this_validator":False,
  "physical_rtx_verified":False,"release_qualified":False,
 }

def validate(models,tools,evidence):
 root=Path(evidence)
 exact_directory(root,("traces","contacts","source-report-consistency.json",
                      "sampled-execution-receipt.json"))
 exact_directory(root/"traces",
      tuple(stage+"-three-mixer.json" for stage in STAGES))
 exact_directory(root/"contacts",
      tuple(name for stage in STAGES for name in (
          stage+"-actual-three-contacts.json",stage+"-contact-progress.json")))
 reported,reported_sha=bounded_json(root/"sampled-execution-receipt.json",MAX_ROOT)
 source_identity(reported)
 require(isinstance(reported.get("stages"),list) and
         [x.get("stage") for x in reported["stages"]]==list(STAGES),
         "incomplete or rearranged paired original-model results")
 consistent,consistent_sha=bounded_json(root/"source-report-consistency.json",
                                        MAX_CONSISTENCY)
 require(reported.get("two_stage_consistency_receipt_sha256")==consistent_sha and
         consistent.get("schema")==paired.SCHEMA and
         consistent.get("sampled_three_pose_count")==108 and
         consistent.get("sampled_evolution_family_admitted") is False and
         consistent.get("reported_sampled_source_no_new_contacts") is True and
         consistent.get("original_donor_sha256")==traces.DONOR and
         consistent.get("model_stages")==list(STAGES) and
         consistent.get("source_original_models_sha_rechecked") is True and
         consistent.get("release_qualified") is False,
         "independent paired source-only consistency receipt differs")
 original_sources=consistent.get("source_results")
 require(isinstance(original_sources,list) and
         [x.get("stage") for x in original_sources]==list(STAGES),
         "missing stage in original paired consistency source results")
 exact_directory(models,tuple(stage+".glb" for stage in STAGES))
 exact_directory(tools,tuple(contact.TOOLS)|{"source-custody.json"})
 for name,pin in contact.TOOLS.items():
  require(digest(Path(tools)/name)==pin,
          "original source triangle contact implementation SHA changed")
 results=[]
 for index,stage in enumerate(STAGES):
  model=Path(models)/(stage+".glb")
  expected,pin=traces.PINS[stage]
  require(model.is_file() and not model.is_symlink() and
          model.stat().st_size==expected and digest(model)==pin,
          "complete original source model GLB SHA differs")
  t,trace_sha=bounded_json(root/"traces"/(stage+"-three-mixer.json"),MAX_TRACE)
  c,contact_sha=bounded_json(root/"contacts"/(stage+"-actual-three-contacts.json"),MAX_CONTACT)
  row=check_stage(stage,reported["stages"][index],t,trace_sha,c,contact_sha,model)
  baseline=original_sources[index]
  require(baseline.get("source_glb_sha256")==pin and
          baseline.get("source_three_trace_sha256")==trace_sha and
          baseline.get("reviewed_contact_report_sha256")==contact_sha and
          baseline.get("new_independent_contact_occurrences")==0 and
          baseline.get("original_three_poses_checked")==54,
          "paired original evidence conflicts with executed source report")
  results.append(row)
 require(sum(x["sampled_three_poses_consistency_checked"] for x in results)==108,
         "source evidence did not cover both complete original models")
 return {
  "schema":SCHEMA,
  "source_operator_receipt_sha256":reported_sha,
  "paired_source_consistency_sha256":consistent_sha,
  "original_model_count":2,
  "source_trace_count":2,
  "source_triangle_report_count":2,
  "sampled_three_pose_consistency_checked":108,
  "original_model_sha256_rechecked":True,
  "source_code_and_three_dependency_sha256_rechecked":True,
  "measured_source_new_independent_contacts":0,
  "reported_uncleared_near_margin_occurrences":
      sum(x["uncleared_near_margin_occurrences"] for x in results),
  "reported_uncleared_attachment_seam_occurrences":
      sum(x["uncleared_attachment_seam_occurrences"] for x in results),
  "actual_mixer_and_geometry_reexecuted_by_this_validator":False,
  "independent_proof_of_process_execution":False,
  "sampled_source_report_consistent":True,
  "source_runtime_was_not_modified_by_this_validator":True,
  "source_original_models_not_adopted":True,
  "all_anatomical_pairs_qualified":False,
  "continuous_collision_qualified":False,
  "arbitrary_browser_playheads_qualified":False,
  "physical_webgl_device_verified":False,
  "artist_approved":False,"physical_rtx_verified":False,
  "remote_original_git_publication_revalidated":False,
  "release_qualified":False,
  "stages":results,
 }

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--models",type=Path,required=True)
 p.add_argument("--reviewed-tools",type=Path,required=True)
 p.add_argument("--evidence",type=Path,required=True)
 p.add_argument("--output",type=Path)
 a=p.parse_args()
 result=validate(a.models,a.reviewed_tools,a.evidence)
 if a.output is not None:
  path=a.output
  require(path.parent.is_dir() and not path.parent.is_symlink()
          and not os.path.lexists(path),
          "new unused independent validation output required")
  with path.open("x",encoding="utf-8") as stream:
   json.dump(result,stream,indent=2,allow_nan=False)
   stream.write("\n");stream.flush();os.fsync(stream.fileno())
 print(json.dumps({k:v for k,v in result.items() if k!="stages"},indent=2))

if __name__=="__main__":
 main()
