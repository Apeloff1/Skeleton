"""Validate recorded V6 true-skinned triangle witnesses without declaring full CCD."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from emerald_v6_tail_clearance import OUTPUTS,PINNED,DONOR,CLIPS

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"assets/emerald/evolution-v6/exported-contact-evidence.json"
PAIRS=["wing_primary_far__torso","wing_mounted_detail__torso","tail__hindlegs"]
EXPECTED_NEAR={
 "pathfinder":{
  "orbit-01":[4892,4888,4892,4892,4894,4896,4865,4696,4797],
  "landing-1":[5032,5033,4995,4893,5231,4441,4219,4660,4709],
 },
 "archivist":{
  "orbit-01":[2563,2561,2561,2563,2563,2561,2551,2532,2555],
  "landing-1":[2741,2736,2722,2717,2800,2643,2577,2684,2692],
 },
}

def require(x,why):
 if not x:raise ValueError(why)

def verify(r):
 require(r.get("schema")=="skeleton.emerald.v6-exported-contact-summary.v1"
         and r.get("donor_sha256")==DONOR
         and r.get("scanned_pairs")==PAIRS
         and r.get("pose_fractions")==[i/8 for i in range(9)]
         and r.get("total_pose_samples")==36
         and r.get("total_anatomical_pair_instances")==108
         and r.get("original_attachment_seam_occurrences")==19836
         and r.get("new_unwelded_contact_occurrences")==0
         and r.get("near_margin_pair_occurrences")==134247,
         "source-bound V6 pose coverage or count changed")
 forms=r.get("forms")
 require(isinstance(forms,list) and len(forms)==2
         and [f.get("stage") for f in forms]==list(EXPECTED_NEAR),
         "expected both original-donor V6 forms")
 previous={"pathfinder":228,"archivist":107}
 near_total=0
 for f in forms:
  stage=f["stage"]
  require((f.get("candidate_bytes"),f.get("candidate_v6_sha256"))==OUTPUTS[stage]
          and f.get("source_v5_sha256")==PINNED[stage][1]
          and f.get("original_v5_nonweld_contacts_in_corresponding_18_samples")==previous[stage]
          and f.get("unapproved_join_blending") is True,
          "stage source, exported model or transition evidence differs")
  poses=f.get("poses")
  require(isinstance(poses,list) and len(poses)==18,
          "missing exact exported pose measurements")
  seen=set()
  for p in poses:
   clip=p.get("clip")
   t=p.get("fraction")
   require(clip in CLIPS and type(t) in (float,int)
           and t in [i/8 for i in range(9)],
           "unsupported clip or non-keyed sample fraction")
   key=(clip,t)
   require(key not in seen,"duplicated pose")
   seen.add(key)
   require(p.get("expected_original_shared_index_contacts")==551
           and type(p.get("new_nonweld_contacts")) is int
           and p["new_nonweld_contacts"]==0
           and type(p.get("near_margin_pairs")) is int
           and p["near_margin_pairs"]==EXPECTED_NEAR[stage][clip][round(8*t)],
           "inconsistent genuine triangle-distance evidence")
   near_total+=p["near_margin_pairs"]
  require(len(seen)==18,"missing source pose records")
 require(near_total==134247,"incomplete near-margin pair count")
 require(all(r.get(k) is False for k in (
     "original_welded_contact_pairs_are_safety_approved",
     "continuous_motion_intervals_qualified",
     "cross_clip_transition_qualified","artistic_approved",
     "physical_rtx_verified","release_qualified")) and
     r.get("unscanned_anatomical_pairs_unqualified") is True,
     "falsely promoted sampled seam data into launch evidence")
 return {
   "schema":"skeleton.emerald.v6.contact-evidence-consistency.v1",
   "model_receipts_match_pins":True,
   "sampled_exported_pose_count":36,
   "anatomical_pair_instances":108,
   "original_source_seam_contact_occurrences":19836,
   "new_independent_contact_occurrences":0,
   "near_margin_pair_occurrences":134247,
   "original_model_bytes_replayed_by_source_only_tests":False,
   "cross_clip_transition_qualified":False,
   "continuous_collision_qualified":False,
   "artist_approved":False,
   "physical_rtx_verified":False,
   "release_qualified":False,
 }

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,default=DEFAULT)
 args=p.parse_args()
 print(json.dumps(verify(json.loads(args.receipt.read_bytes())),indent=2))
