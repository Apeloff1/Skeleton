"""Run BOTH original V7 GLBs through real Three 0.186 and reviewed contact analysis.

Unlike the source-only JSON consistency gate, this operator executes
all 108 real mixer poses and reviewed skinned-triangle contact scans itself.
Its conditional sampled-only acceptance is never release, continuous CCD,
full anatomy, real browser GPU, original model publication or artwork approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading

import admit_emerald_v7_three_mixer_pair as consistency
import check_emerald_v7_three_mixer_trace as traces
import emerald_v6_crossfade_screen as geometry

ROOT=Path(__file__).resolve().parents[1]
NODE=ROOT/"frontend/scripts/emerald-v7-three-mixer-trace.mjs"
PYTHON_CONTACT=ROOT/"scripts/qualify_emerald_v7_three_trace_contacts.py"
SCHEMA="skeleton.emerald.v7.operated-three-and-triangles.sampled-only.v1"
STAGES=("pathfinder","archivist")
MAX_RUNTIME=7200
NODE_TIMEOUT=360
NODE_VERSION="24"
THREE_VERSION="0.186.1"
MIN_FREE_BYTES=96*1024*1024
MAX_STDOUT=16384
MAX_CHILD_OUTPUT_BYTES=8*1024*1024
MAX_NODE_BINARY_BYTES=384*1024*1024
SOURCE_FILES={
 "three_mixer":NODE,
 "triangle_contacts":PYTHON_CONTACT,
 "paired_source_gate":ROOT/"scripts/admit_emerald_v7_three_mixer_pair.py",
 "trace_validator":ROOT/"scripts/check_emerald_v7_three_mixer_trace.py",
 "operator":Path(__file__).resolve(),
}
THREE_RUNTIME_FILES={
 "three_core":ROOT/"frontend/node_modules/three/build/three.core.js",
 "three_module":ROOT/"frontend/node_modules/three/build/three.module.js",
 "three_manifest":ROOT/"frontend/node_modules/three/package.json",
}

def source_hashes(mapping):
 require(all(p.is_file() and not p.is_symlink() for p in mapping.values()),
         "source replay code or runtime dependency missing or unexpectedly linked")
 return {name:digest(path) for name,path in mapping.items()}


def require(value,why):
 if not value:raise ValueError(why)

def digest(path):
 with Path(path).open("rb") as reader:
  return hashlib.file_digest(reader,"sha256").hexdigest()

def sanitize_env():
 """Discard inherited Python, Node, shell/preload, credential and proxy state."""
 allow=("PATH","HOME","TMPDIR","TEMP","TMP","LANG","LC_ALL","SYSTEMROOT","WINDIR")
 env={key:os.environ[key] for key in allow if key in os.environ}
 env.update({"PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1",
             "NODE_NO_WARNINGS":"0"})
 return env

def resolve_node_binary(executable):
 """Resolve a concrete executable and pin its full bytes, not only --version."""
 require(isinstance(executable,str) and executable,
         "missing Node 24 operator binary")
 discovered=shutil.which(executable)
 require(discovered is not None,"Node 24 executable is missing")
 candidate=Path(discovered).absolute()
 require(candidate.is_file() and not candidate.is_symlink()
         and os.access(candidate,os.X_OK)
         and 4096<=candidate.stat().st_size<=MAX_NODE_BINARY_BYTES,
         "trusted executable Node 24 binary required (no links or wrappers)")
 stat_before=candidate.stat()
 actual_sha=digest(candidate)
 stat_after=candidate.stat()
 require((stat_before.st_dev,stat_before.st_ino,stat_before.st_size,
          stat_before.st_mtime_ns,stat_before.st_ctime_ns)==
         (stat_after.st_dev,stat_after.st_ino,stat_after.st_size,
          stat_after.st_mtime_ns,stat_after.st_ctime_ns),
         "Node runtime changed during original binary hash verification")
 return {"path":str(candidate),"sha256":actual_sha,"bytes":stat_after.st_size}


def closed_subprocess(args,cwd,timeout,allowed=(0,),env=None):
 """Shell-free child, bounded live output and kill-on-quota/timeout.

 subprocess.run(..., stdout=PIPE) can allocate unbounded memory, while
 redirecting to an unbounded tempfile can consume the entire local disk.
 Two bounded streaming readers drain both pipes until exit, killing a child
 that violates the output budget. They never publish raw stdout/stderr.
 """
 require(isinstance(args,list) and len(args)>=2
         and all(isinstance(x,str) and x for x in args),
         "unsafe executable argument vector")
 require(type(timeout) in (float,int) and
         math.isfinite(timeout) and 0<timeout<=MAX_RUNTIME+180,
         "unbounded operator subprocess")
 require(type(MAX_CHILD_OUTPUT_BYTES) is int and
         65536<=MAX_CHILD_OUTPUT_BYTES<=64*1024*1024,
         "unqualified child output quota")
 proc=subprocess.Popen(args,cwd=str(cwd),
                       env=env if env is not None else sanitize_env(),
                       stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       shell=False)
 tails={"stdout":bytearray(),"stderr":bytearray()}
 over=threading.Event()
 faults=[]
 def pump(name,stream):
  seen=0
  try:
   while True:
    chunk=stream.read(65536)
    if not chunk:break
    seen+=len(chunk)
    tails[name]=(tails[name]+chunk)[-MAX_STDOUT:]
    if seen>MAX_CHILD_OUTPUT_BYTES:
     over.set()
     try:proc.kill()
     except ProcessLookupError:pass
     break
  except OSError as exc:
   faults.append(str(exc))
  finally:
   stream.close()
 threads=[
  threading.Thread(target=pump,args=("stdout",proc.stdout),daemon=True),
  threading.Thread(target=pump,args=("stderr",proc.stderr),daemon=True),
 ]
 for worker in threads:worker.start()
 timed_out=False
 try:
  proc.wait(timeout=timeout)
 except subprocess.TimeoutExpired:
  timed_out=True
  proc.kill()
  proc.wait()
 finally:
  for worker in threads:worker.join(timeout=5)
  for pipe in (proc.stdout,proc.stderr):
   if not pipe.closed:pipe.close()
 require(not timed_out,"original Three/mixer or geometry subprocess time limit exceeded")
 require(not over.is_set(),"original Three/mixer or geometry child output quota exceeded")
 require(not faults,"original child pipe reader failed: "+str(faults[0]))
 stdout=bytes(tails["stdout"]).decode("utf-8","replace")
 stderr=bytes(tails["stderr"]).decode("utf-8","replace")
 require(proc.returncode in allowed,
         "original Three/mixer or triangle scan failed with code "+
         str(proc.returncode)+": "+(stderr or stdout)[-6000:])
 return {"exit_code":proc.returncode,
         "stdout_tail":stdout[-400:],"stderr_tail":stderr[-400:]}


def source_admission(model_dir,tool_dir,destination,node_executable):
 model_dir=Path(model_dir).resolve(strict=True)
 tool_dir=Path(tool_dir).resolve(strict=True)
 destination=Path(destination).resolve(strict=False)
 require(model_dir.is_dir() and tool_dir.is_dir()
         and not model_dir.is_symlink() and not tool_dir.is_symlink(),
         "trusted local original models and SHA-reviewed source directories required")
 require(ROOT.exists() and all(x.is_file() and not x.is_symlink()
          for x in (NODE,PYTHON_CONTACT,ROOT/"scripts/admit_emerald_v7_three_mixer_pair.py",
                    ROOT/"scripts/check_emerald_v7_three_mixer_trace.py")),
         "missing trusted source-bound Three/geometry scripts")
 require(not destination.is_relative_to(ROOT.resolve())
         and not destination.is_relative_to(model_dir)
         and not destination.is_relative_to(tool_dir)
         and destination.parent.is_dir()
         and not destination.parent.is_symlink()
         and not os.path.lexists(destination),
         "unused external original source qualification directory required")
 require(shutil.disk_usage(destination.parent).free>=MIN_FREE_BYTES,
         "insufficient original source-evidence scratch storage")
 models={}
 for stage in STAGES:
  model=model_dir/(stage+".glb")
  expected,sha=traces.PINS[stage]
  require(model.is_file() and not model.is_symlink()
          and model.stat().st_size==expected and digest(model)==sha,
          "exact original V7 GLB is missing or modified: "+stage)
  models[stage]={"path":str(model),"bytes":expected,"sha256":sha}
 # Vetted code is run only after checking the hashes of ALL five imports.
 # Avoid PYTHONPATH and sys.modules injection from the calling environment.
 verified=geometry.vetted_tools(tool_dir)
 require(len(verified)==2 and len(geometry.TOOLS)==5,
         "source geometry tool dependency chain differs")
 three_package=ROOT/"frontend/node_modules/three/package.json"
 require(three_package.is_file() and
         three_package.stat().st_size<=64*1024 and
         json.loads(three_package.read_bytes()).get("version")==THREE_VERSION,
         "Three 0.186.1 must be installed from the trusted frontend lockfile")
 source_sha=source_hashes(SOURCE_FILES)
 runtime_sha=source_hashes(THREE_RUNTIME_FILES)
 node_identity=resolve_node_binary(str(node_executable))
 runtime=closed_subprocess(
      [node_identity["path"],"--version"],ROOT/"frontend",15)
 require(re.fullmatch(r"v24\.\d+\.\d+",runtime["stdout_tail"].strip()) is not None,
         "Three operator requires approved Node 24")
 return {"models":models,"tools":str(tool_dir),
         "node_executable":node_identity["path"],
         "node_binary_sha256":node_identity["sha256"],
         "node_binary_bytes":node_identity["bytes"],
         "node_version":runtime["stdout_tail"].strip(),
         "three_version":THREE_VERSION,
         "source_sha256":source_sha,
         "three_runtime_sha256":runtime_sha}

def operate_one(stage,model_path,tool_dir,output_root,node_executable,budget):
 assert stage in STAGES
 output_root=Path(output_root)
 traces_dir=output_root/"traces"
 contacts_dir=output_root/"contacts"
 trace=traces_dir/(stage+"-three-mixer.json")
 report=contacts_dir/(stage+"-actual-three-contacts.json")
 checkpoint=contacts_dir/(stage+"-contact-progress.json")
 node_result=closed_subprocess([
     node_executable,str(NODE),"--stage",stage,"--model",str(model_path),
     "--samples","9","--output",str(trace)],
     ROOT/"frontend",NODE_TIMEOUT)
 require(trace.is_file() and trace.stat().st_size<=traces.MAX_REPORT_BYTES,
         "actual Three mixer failed to produce bounded source trace")
 trace_value=json.loads(trace.read_bytes())
 checked=traces.verify(trace_value,stage,model_path)
 require(checked["sampled_poses"]==54 and
         checked["full_model_sha_independently_rechecked"] is True,
         "missing actual 54 source poses or independent original V7 GLB SHA")
 contact_result=closed_subprocess([
     sys.executable,str(PYTHON_CONTACT),"--stage",stage,
     "--model",str(model_path),"--tools",str(tool_dir),
     "--trace",str(trace),"--output",str(report),
     "--checkpoint",str(checkpoint),
     "--time-budget-seconds",str(budget)],
     ROOT, budget+150)
 require(report.is_file() and report.stat().st_size<=consistency.CONTACT_BUDGET,
         "actual Three source contacts absent or oversized")
 actual=json.loads(report.read_bytes())
 counted=consistency.verify_contact(actual,stage,trace_value,digest(trace))
 require(counted["new_independent_contact_occurrences"]==0,
         "original Three mixer creates independent skinned-triangle contacts")
 return {"stage":stage,
         "original_v7_model_sha256":checked["original_model_sha256"],
         "actual_three_source_trace_sha256":digest(trace),
         "reviewed_triangle_report_sha256":digest(report),
         "actual_three_mixer_process_executed":node_result["exit_code"]==0,
         "reviewed_triangle_process_executed":contact_result["exit_code"]==0,
         "sampled_poses":counted["original_three_poses_checked"],
         "source_region_pair_types":counted["reviewed_anatomical_pair_types"],
         "new_independent_contact_occurrences":counted["new_independent_contact_occurrences"],
         "uncleared_near_margin_occurrences":counted["unqualified_8mm_near_margin_occurrences"],
         "uncleared_attachment_seam_occurrences":counted["unqualified_inherited_attachment_seam_occurrences"],
         "independent_world_matrix_error_max":counted["worst_independent_world_matrix_error"],
         "full_continuous_collision_qualified":False,
         "physical_rtx_verified":False,
         "release_qualified":False}

def execute(models_dir,tools_dir,output_dir,node_executable="node",budget=1200):
 require(type(budget) in (int,float) and math.isfinite(budget)
         and 60<=budget<=MAX_RUNTIME,
         "unsafe original-source contact runtime budget")
 identity=source_admission(models_dir,tools_dir,output_dir,node_executable)
 destination=Path(output_dir).resolve(strict=False)
 lock=destination.parent/("."+destination.name+".three-pair.lock")
 require(not os.path.lexists(lock),"concurrent original source qualifier")
 lock.mkdir(mode=0o700)
 try:
  with tempfile.TemporaryDirectory(
      dir=destination.parent,prefix=".emerald-v7-actual-three-") as location:
   temp=Path(location)
   for name in ("traces","contacts"): (temp/name).mkdir(mode=0o700)
   evaluations=[]
   for stage in STAGES:
    result=operate_one(stage,identity["models"][stage]["path"],
                       identity["tools"],temp,
                       identity["node_executable"],budget)
    evaluations.append(result)
   consistency_path=temp/"source-report-consistency.json"
   consistent=consistency.admit(
       models_dir,temp/"traces",temp/"contacts",consistency_path)
   require(consistent["sampled_evolution_family_admitted"] is False and
           consistent["sampled_three_pose_count"]==108 and
           consistent["reported_sampled_source_no_new_contacts"] is True,
           "paired source-only consistency gate changed approval policy")
   require(len(evaluations)==2 and
           sum(x["sampled_poses"] for x in evaluations)==108 and
           all(x["actual_three_mixer_process_executed"] is True and
               x["reviewed_triangle_process_executed"] is True
               for x in evaluations),
           "missing actual original V7 mixer or sampled geometry execution")
   require(source_hashes(SOURCE_FILES)==identity["source_sha256"] and
           source_hashes(THREE_RUNTIME_FILES)==identity["three_runtime_sha256"],
           "Three or original contact source changed during operator execution")
   # A checked version string alone is not executable custody. Rehash the
   # concrete binary that actually launched the mixer after both stage runs.
   node_now=resolve_node_binary(identity["node_executable"])
   require((node_now["sha256"],node_now["bytes"])==
           (identity["node_binary_sha256"],identity["node_binary_bytes"]),
           "Node runtime executable changed while original GLBs were replayed")
   for filename,pin in geometry.TOOLS.items():
    require(geometry.sha(Path(identity["tools"])/filename)==pin,
            "reviewed original contact source mutated during operator execution")
   for stage in STAGES:
    model=Path(identity["models"][stage]["path"])
    expected,sha=traces.PINS[stage]
    require(model.is_file() and not model.is_symlink() and
            (model.stat().st_size,digest(model))==(expected,sha),
            "source original V7 GLB moved or changed during operator execution")
   receipt={
     "schema":SCHEMA,"donor_sha256":traces.DONOR,
     "original_model_count":2,"original_stage_order":list(STAGES),
     "original_glb_byte_total":sum(x["bytes"] for x in identity["models"].values()),
     "real_three_package_version":identity["three_version"],
     "node_runtime_version":identity["node_version"],
     "node_executable_sha256":identity["node_binary_sha256"],
     "node_executable_bytes":identity["node_binary_bytes"],
     "exact_model_sha_rechecked_before_and_after":True,
     "source_geometry_hashes":geometry.TOOLS,
     "source_script_sha256":identity["source_sha256"],
     "installed_three_runtime_file_sha256":identity["three_runtime_sha256"],
     "two_stage_consistency_receipt_sha256":digest(consistency_path),
     "sampled_three_mixer_poses_executed":108,
     "reviewed_anatomical_pair_types":3,
     "source_operator_executed_mixer":True,
     "source_operator_executed_triangle_contact":True,
     "source_operator_sampled_only_qualified":True,
     "original_model_auto_adopted":False,
     "all_anatomical_pairs_qualified":False,
     "arbitrary_browser_loop_playheads_qualified":False,
     "continuous_collision_qualified":False,
     "browser_webgl_device_tested":False,
     "artist_approved":False,
     "unreal_compiled":False,
     "physical_rtx_verified":False,
     "remote_original_git_publication_verified":False,
     "independent_runtime_binary_signature_attested":False,
     "release_qualified":False,
     "stages":evaluations,
   }
   require(receipt["original_glb_byte_total"]==229515688,
           "original two-model source extent changed")
   with (temp/"sampled-execution-receipt.json").open("x",encoding="utf-8") as stream:
    json.dump(receipt,stream,indent=2,allow_nan=False)
    stream.write("\n");stream.flush();os.fsync(stream.fileno())
   require(not os.path.lexists(destination),
           "original source target appeared during qualification")
   os.rename(temp,destination)
   return receipt
 finally:
  lock.rmdir()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--models",type=Path,required=True)
 p.add_argument("--reviewed-tools",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 p.add_argument("--node",default="node")
 p.add_argument("--budget-seconds-per-stage",type=float,default=1200)
 a=p.parse_args()
 result=execute(a.models,a.reviewed_tools,a.output,
                a.node,a.budget_seconds_per_stage)
 print(json.dumps({key:value for key,value in result.items()
                   if key!="stages"},indent=2))
if __name__=="__main__":main()
