"""Check original-donor crossfade screen reports without fabricating safe intervals."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

from emerald_v6_crossfade_screen import (
 DONOR,MODELS,TOOLS,TRANSITIONS,PAIRS,MARGIN,CROSSFADE_SECONDS,
)

def require(condition, why):
 if not condition:raise ValueError(why)

def verify(value, expected_stage):
 require(expected_stage in MODELS and
         value.get("schema")=="skeleton.emerald.v6.crossfade-mesh-screen.v1" and
         value.get("stage")==expected_stage and
         (value.get("model_bytes"),value.get("model_sha256"))==MODELS[expected_stage] and
         value.get("donor_sha256")==DONOR and
         value.get("reviewed_tool_digests")==TOOLS and
         value.get("source_crossfade_seconds")==CROSSFADE_SECONDS and
         value.get("clip_transitions")==[list(x) for x in TRANSITIONS],
         "untrusted exact-model or crossfade policy receipt")
 steps=value.get("steps_per_transition")
 require(type(steps) is int and 3<=steps<=17 and
         value.get("total_sampled_blends")==len(TRANSITIONS)*steps,
         "incomplete or fabricated sampling quota")
 entries=value.get("samples")
 require(isinstance(entries,list) and len(entries)==len(TRANSITIONS)*steps,
         "truncated animation transition matrix")
 total=0
 unresolved=0
 for index,row in enumerate(entries):
  left,right=TRANSITIONS[index//steps]
  fraction=(index%steps)/(steps-1)
  require(row.get("from_clip")==left and row.get("to_clip")==right and
          math.isfinite(row.get("alpha",float("nan"))) and
          abs(row["alpha"]-fraction)<1e-12,
          "reordered or duplicated crossfade sample")
  require(type(row.get("new_independent_contact_pairs")) is int and
          row["new_independent_contact_pairs"]>=0 and
          type(row.get("shared_index_bind_seam_candidates")) is int and
          row["shared_index_bind_seam_candidates"]>=0 and
          type(row.get("within_8mm_not_contact")) is int and
          row["within_8mm_not_contact"]>=0,
          "invalid collision measurement")
  pairs=row.get("pairs")
  require(isinstance(pairs,list) and len(pairs)==len(PAIRS),
          "incomplete source pair inventory")
  require([x.get("pair") for x in pairs]==[a+"__"+b for a,b in PAIRS],
          "pair identity switched")
  for pair in pairs:
   require(type(pair.get("new_independent_contact_pairs")) is int and
           pair["new_independent_contact_pairs"]>=0 and
           type(pair.get("shared_index_bind_seam_candidates")) is int and
           pair["shared_index_bind_seam_candidates"]>=0 and
           type(pair.get("within_8mm_not_contact")) is int and
           pair["within_8mm_not_contact"]>=0 and
           type(pair.get("candidate_pairs")) is int and
           pair["candidate_pairs"]>=0,
           "invalid anatomical witness")
  require(sum(x["new_independent_contact_pairs"] for x in pairs)==row["new_independent_contact_pairs"]
          and sum(x["shared_index_bind_seam_candidates"] for x in pairs)==row["shared_index_bind_seam_candidates"]
          and sum(x["within_8mm_not_contact"] for x in pairs)==row["within_8mm_not_contact"],
          "pair measurements do not reconcile to sample")
  total+=row["new_independent_contact_pairs"]
  unresolved+=row["new_independent_contact_pairs"]>0
 require(total==value.get("observed_new_contact_instances")
         and unresolved==value.get("sampled_blends_with_new_contacts"),
         "aggregate contact evidence differs")
 require(value.get("all_transition_intervals_qualified") is False
         and value.get("tested_in_real_browser_mixer") is False
         and value.get("continuous_collision_qualified") is False
         and value.get("unexamined_rig_seams_qualified") is False
         and value.get("optional_equipment_enabled") is False
         and value.get("artist_approved") is False
         and value.get("physical_rtx_verified") is False
         and value.get("release_qualified") is False,
         "false complete collision, device or release qualification")
 return {
  "stage":expected_stage,
  "sha256":MODELS[expected_stage][1],
  "sampled_blends":len(entries),
  "sampled_blends_with_witnesses":unresolved,
  "new_contact_occurrences":total,
  "source_receipt_consistent":True,
  "real_three_mixer_qualified":False,
  "continuous_collision_qualified":False,
  "release_qualified":False,
 }

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,required=True)
 p.add_argument("--stage",required=True,choices=MODELS)
 a=p.parse_args()
 print(json.dumps(verify(json.loads(a.receipt.read_bytes()),a.stage),indent=2))
