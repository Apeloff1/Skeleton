"""Reject tampered model census receipts and false collision/artistic claims.

This validates recorded figures, not the original model bytes: re-run the
separate GLB anatomy scanner for genuine source evidence.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from emerald_v5_anatomical_census import PINNED, COHORTS, DONOR_SHA, RISK_PAIRS

ROOT=Path(__file__).resolve().parents[1]
RECEIPT=ROOT/"assets/emerald/evolution-v5/anatomical-census-measured.json"
EXPECTED={
 "torso":224140,"head":44618,"forelegs":20728,"hindlegs":17918,
 "tail":43160,"wing_primary_near":0,"wing_primary_far":260,
 "wing_mounted_detail":78,"wing_flight_near":144912,
 "wing_flight_far":143876,"rig_correctives":79538,"three_way_mixed":84
}

def require(x,msg):
 if not x:raise ValueError(msg)

def verify(r):
 require(r.get("schema")=="skeleton.emerald.measured-anatomical-census.v1"
         and r.get("donor_sha256")==DONOR_SHA
         and r.get("previous_strict_anatomy_count")==269919
         and r.get("majority_assigned_count")==719228
         and r.get("ambiguous_three_way_count")==84
         and r.get("cohort_counts")==EXPECTED
         and sum(EXPECTED.values())==719312,"untrusted anatomy census")
 require(r.get("blended_seam_threshold_fraction")==.2
         and r.get("multi_cohort_vertices")==83627
         and r.get("triangles_touching_multi_influence_vertices")==171165
         and r.get("triangles_with_three_or_more_supported_cohorts")==17222
         and r.get("blended_seam_contact_qualified") is False,
         "mixed-influence seams missing or misleading")
 rows=r.get("verified_exact_local_model_runs")
 require(isinstance(rows,list) and len(rows)==7,"missing measured source files")
 seen=set()
 for x in rows:
  stage,version=x["stage"],x["version"];key=(stage,version)
  require(key in PINNED and key not in seen,"unexpected or duplicate source")
  seen.add(key)
  require((x.get("bytes"),x.get("sha256"))==PINNED[key]
          and x.get("triangle_count")==719312
          and x.get("majority_assigned")==719228
          and x.get("three_way_mixed")==84
          and x.get("prior_classified")==269919
          and x.get("prior_unclassified")==449393,"source model measured data changed")
 require(seen==set(PINNED)-{("scholar","v5")},"unexpected model evidence coverage")
 require(r.get("unqualified_contact_triangles")==719312
         and r.get("completed_full_contact_pairings")==0
         and all(r.get(k) is False for k in
             ("continuous_collision_qualified","optional_equipment_enabled",
              "physical_rtx_verified","artist_approved","release_qualified")),
         "source census must not authorize clearance or publication")
 require(len(COHORTS)==11 and len(RISK_PAIRS)>=15,
         "anatomical contact worklist was weakened")
 return {"schema":"skeleton.emerald.census-consistency-check.v1",
         "exact_pinned_model_receipts":len(rows),
         "anatomical_cohorts":len(COHORTS),
         "majority_assigned_triangles":719228,
         "mixed_three_way_triangles":84,
         "blended_skin_risk_triangles":171165,
         "remaining_unqualified_contact_triangles":719312,
         "recorded_census_consistent":True,
         "actual_models_replayed_in_ci":False,
         "continuous_collision_qualified":False,
         "artist_approved":False,"release_qualified":False}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,default=RECEIPT)
 args=p.parse_args()
 print(json.dumps(verify(json.loads(args.receipt.read_bytes())),indent=2))

if __name__=="__main__":main()
