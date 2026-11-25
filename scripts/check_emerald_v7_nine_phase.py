"""Reconcile 108 V7 exported crossfade poses, with optional original report replay.

A complete *sampled* audit is never continuous CCD or browser/device approval.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from emerald_v7_orbit02 import OUTPUTS,DONOR
from emerald_v6_crossfade_screen import TRANSITIONS,PAIRS,CROSSFADE_SECONDS,TOOLS

DEFAULT=Path(__file__).resolve().parents[1]/"assets/emerald/evolution-v7/nine-phase-complete-evidence.json"
STAGES=("pathfinder","archivist")
SHA={"pathfinder":"78953a55fa755c986ab196553fd4c1bfacee8cf9aeb9766b92eb6af6301359ee",
     "archivist":"3710a5b66e6158e5695f4f441c78a29001bb3f26ffe5b3a71c2a498c1c1c8dbf"}
FULL_REPORT_BYTES={"pathfinder":63829,"archivist":63693}
TOOL="0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f"

def require(condition,msg):
 if not condition:raise ValueError(msg)

def digest(path):
 with Path(path).open("rb") as stream:
  return hashlib.file_digest(stream,"sha256").hexdigest()

def verify_full_report(report, form, expected_counts):
 """Validate real runner-shaped sample and tool metadata, not just a digest.

 This validates the source/geometry contract. The caller must separately
 verify each external report's exact byte length and pinned SHA-256.
 """
 stage=form["stage"]
 require(report.get("schema") in (
             "skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1",
             "skeleton.emerald.v6.crossfade-mesh-screen.v1")
         and report.get("stage")==stage
         and report.get("model_bytes")==form["bytes"]
         and report.get("model_sha256")==form["sha256"]
         and report.get("donor_sha256")==DONOR,
         "source GLB or report schema differs")
 # The committed crossfade runner calls this field
 # 'reviewed_tool_digests'. Historical external reports use 'source_tools'.
 # Accept either only with the verified contact auditor digest, and reject
 # contradictory simultaneous provenance declarations.
 newer=report.get("reviewed_tool_digests")
 legacy=report.get("source_tools")
 require(isinstance(newer,dict) or isinstance(legacy,dict),
         "original contact auditor provenance is missing")
 if newer is not None:
  require(newer==TOOLS,"reviewed geometry tool library differs")
 if legacy is not None:
  require(isinstance(legacy,dict)
          and legacy.get("contact_audit.py")==TOOL,
          "legacy auditor digest differs")
 require(report.get("source_crossfade_seconds",CROSSFADE_SECONDS)==CROSSFADE_SECONDS
         and report.get("steps_per_transition")==9
         and report.get("total_sampled_blends")==54
         and report.get("clip_transitions")==[list(route) for route in TRANSITIONS],
         "crossfade source duration or source clip matrix changed")
 for key in ("all_transition_intervals_qualified","tested_in_real_browser_mixer",
             "continuous_collision_qualified","unexamined_rig_seams_qualified",
             "optional_equipment_enabled","artist_approved",
             "physical_rtx_verified","release_qualified"):
  require(report.get(key) is False,
          "measured report attempts unverified real-time or release acceptance")
 rows=report.get("samples")
 require(isinstance(rows,list) and len(rows)==54,
         "full source report lacks 54 sampled poses")
 new_total=near_total=weld_total=0
 for i,row in enumerate(rows):
  outgoing,incoming=TRANSITIONS[i//9]
  require(row.get("from_clip")==outgoing
          and row.get("to_clip")==incoming
          and type(row.get("alpha")) in (int,float)
          and math.isfinite(row["alpha"]) and abs(row["alpha"]-(i%9)/8)<1e-12
          and type(row.get("new_independent_contact_pairs")) is int
          and row["new_independent_contact_pairs"]==0
          and type(row.get("shared_index_bind_seam_candidates")) is int
          and row["shared_index_bind_seam_candidates"]==551
          and type(row.get("within_8mm_not_contact")) is int
          and row["within_8mm_not_contact"]==expected_counts[i//9][i%9],
          "full source pose measurement or ordering changed")
  pairs=row.get("pairs")
  require(isinstance(pairs,list)
          and [p.get("pair") for p in pairs]==[a+"__"+b for a,b in PAIRS],
          "full per-region original contact-pair identity changed")
  for p in pairs:
   require(all(type(p.get(field)) is int and p[field]>=0 for field in (
               "new_independent_contact_pairs","shared_index_bind_seam_candidates",
               "within_8mm_not_contact","candidate_pairs","broadphase_visits")),
           "full per-region original witness count malformed")
  require(sum(p["new_independent_contact_pairs"] for p in pairs)==0
          and sum(p["shared_index_bind_seam_candidates"] for p in pairs)==551
          and sum(p["within_8mm_not_contact"] for p in pairs)==expected_counts[i//9][i%9],
          "full per-region original triangle witnesses altered")
  new_total+=row["new_independent_contact_pairs"]
  near_total+=row["within_8mm_not_contact"]
  weld_total+=row["shared_index_bind_seam_candidates"]
 require(report.get("observed_new_contact_instances")==new_total==0
         and report.get("sampled_blends_with_new_contacts")==0,
         "recorded source report misstates complete contact tally")
 return {"stage":stage,"validated_rows":len(rows),
         "new_contacts":new_total,"near_margin_pairs":near_total,
         "attachment_seam_occurrences":weld_total,
         "full_continuous_collision_qualified":False}


def verify(summary,report_directory=None):
 require(summary.get("schema")=="skeleton.emerald.v7.nine-phase-complete.v1"
         and summary.get("donor_sha256")==DONOR
         and summary.get("auditor_sha256")==TOOL
         and summary.get("blend_seconds")==CROSSFADE_SECONDS
         and summary.get("margin_m")==.008
         and summary.get("routes")==[list(route) for route in TRANSITIONS]
         and summary.get("phase_fractions")==[i/8 for i in range(9)]
         and summary.get("contact_pairs")==[a+"__"+b for a,b in PAIRS],
         "source-bound exact original model/method or stage matrix differs")
 forms=summary.get("forms")
 require(isinstance(forms,list) and len(forms)==2
         and tuple(f.get("stage") for f in forms)==STAGES,
         "two distinct measured V7 models required")
 near_total=weld_total=pose_total=0
 original_files_verified=0
 for f in forms:
  stage=f["stage"]
  require((f.get("bytes"),f.get("sha256"))==OUTPUTS[stage]
          and f.get("full_report_sha256")==SHA[stage]
          and f.get("full_report_bytes")==FULL_REPORT_BYTES[stage]
          and f.get("full_report_filename")==stage+"-nine-phase-contact-report.json"
          and f.get("poses")==54
          and f.get("source_inherited_welds_per_pose")==551
          and f.get("new_contacts_per_pose")==0
          and f.get("resumed_from_exact_checkpoint") is (stage=="pathfinder"),
          "changed V7 output identity, interrupted run or sample receipt")
  counts=f.get("near_margin_counts_by_route")
  require(isinstance(counts,list) and len(counts)==len(TRANSITIONS)
          and all(isinstance(route,list) and len(route)==9
                  and all(type(v) is int and v>=0 for v in route)
                  for route in counts), "source pose/phase receipt truncated")
  near_total+=sum(sum(route) for route in counts)
  weld_total+=54*551;pose_total+=54
  if report_directory is None:continue
  path=Path(report_directory)/f["full_report_filename"]
  require(path.is_file() and not path.is_symlink()
          and path.stat().st_size==f["full_report_bytes"]
          and digest(path)==f["full_report_sha256"],
          "full original 54-pose report bytes differ")
  report=json.loads(path.read_bytes())
  verify_full_report(report,f,counts)
  original_files_verified+=1
 require(pose_total==summary.get("total_poses")==108
         and summary.get("total_new_contacts")==0
         and near_total==summary.get("total_near_margin_occurrences")==415154
         and weld_total==summary.get("total_source_weld_occurrences")==59508,
         "incomplete contact sum or suppressed near-margin pair")
 require(all(summary.get(flag) is False for flag in (
     "all_other_anatomical_pairs_qualified",
     "all_arbitrary_playheads_qualified","continuous_time_collision_qualified",
     "real_three_mixer_qualified","artist_approved","physical_rtx_verified",
     "remote_binary_publication_verified","release_qualified")),
     "sampled proof falsely elevated to continuous, device or release acceptance")
 return {"schema":"skeleton.emerald.v7.nine-phase-consistency.v1",
         "pinned_original_form_count":2,"complete_sampled_pose_count":108,
         "new_contact_witnesses":0,"near_margin_pair_occurrences":415154,
         "uncleared_attachment_seam_occurrences":59508,
         "exact_full_reports_verified":original_files_verified,
         "original_binary_models_replayed_by_this_validator":False,
         "real_three_mixer_qualified":False,"continuous_collision_qualified":False,
         "artist_approved":False,"release_qualified":False}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--summary",type=Path,default=DEFAULT)
 p.add_argument("--reports-dir",type=Path)
 args=p.parse_args()
 print(json.dumps(verify(json.loads(args.summary.read_bytes()),args.reports_dir),indent=2))

if __name__=="__main__":main()
