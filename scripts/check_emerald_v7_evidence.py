"""Validate real V7 exported-contact summary without inventing CCD approval."""
import argparse,json
from pathlib import Path
from emerald_v7_orbit02 import OUTPUTS,SOURCES,DONOR,ROOT_JOINT,TARGET_CLIP
from emerald_v6_crossfade_screen import TRANSITIONS,PAIRS,CROSSFADE_SECONDS

DEFAULT=Path(__file__).resolve().parents[1]/"assets/emerald/evolution-v7/orbit02-exported-crossfade-summary.json"
PREVIOUS={"pathfinder":15,"archivist":5}
NEAR={"pathfinder":89988,"archivist":49477}

def require(ok,msg):
 if not ok:raise ValueError(msg)

def verify(receipt):
 require(receipt.get("schema")=="skeleton.emerald.v7.exact-exported-crossfade-summary.v1"
         and receipt.get("original_hoarder_donor_sha256")==DONOR
         and receipt.get("routes")==[list(x) for x in TRANSITIONS]
         and receipt.get("fractions")==[0,.5,1]
         and receipt.get("margin_m")==.008
         and receipt.get("reviewed_anatomical_pairs")==[a+"__"+b for a,b in PAIRS],
         "source-bound contact method or route identity changed")
 forms=receipt.get("forms")
 require(isinstance(forms,list) and len(forms)==2 and
         [x.get("stage") for x in forms]==list(PREVIOUS),
         "missing or swapped exact V7 model")
 for f in forms:
  stage=f["stage"]
  require((f.get("v7_bytes"),f.get("v7_sha256"))==OUTPUTS[stage]
          and f.get("source_v6_sha256")==SOURCES[stage][1]
          and f.get("corrected_animation")==TARGET_CLIP
          and f.get("corrected_tail_joint_index")==ROOT_JOINT
          and f.get("modified_quaternion_keys")==160
          and f.get("unchanged_other_channels")==44512
          and f.get("old_v6_new_contacts")==PREVIOUS[stage]
          and f.get("new_v7_new_contacts")==0
          and f.get("poses_sampled")==18
          and f.get("unchanged_attachment_seam_occurrences")==9918
          and f.get("new_v7_near_margin_pair_occurrences")==NEAR[stage],
          "wrong exact exported model or incomplete pose witnesses")
 require(receipt.get("total_sampled_blends")==36
         and receipt.get("original_new_contacts")==20
         and receipt.get("corrected_new_contacts")==0
         and receipt.get("total_preexisting_shared_index_seam_occurrences")==19836
         and receipt.get("total_near_margin_pair_occurrences")==139465,
         "inflated or suppressed contact counts")
 require(receipt.get("original_evolution_models_unmodified") is True
         and all(receipt.get(flag) is False for flag in (
          "all_anatomical_pairs_qualified","all_crossfade_loop_phases_qualified",
          "continuous_motion_intervals_qualified","real_three_mixer_qualified",
          "optional_equipment_enabled","artist_approved","physical_rtx_verified",
          "release_qualified")),
         "source evidence falsely promotes physical, artistic or release acceptance")
 return {
  "schema":"skeleton.emerald.v7.source-evidence-consistency.v1",
  "model_pin_count":2,"total_sampled_blends":36,
  "original_witnesses":20,"new_v7_witnesses":0,
  "remaining_near_margin_pairs":139465,
  "welded_attachment_occurrences_not_cleared":19836,
  "source_ledger_consistent":True,
  "real_exported_models_rerun_in_source_ci":False,
  "continuous_collision_qualified":False,
  "real_three_mixer_qualified":False,
  "artist_approved":False,"release_qualified":False,
 }

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,default=DEFAULT)
 a=p.parse_args()
 print(json.dumps(verify(json.loads(a.receipt.read_bytes())),indent=2))
