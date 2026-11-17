"""Fail-closed consistency for recorded 266 exact-model AABB screenings.

Receipt consistency is NOT an independent replay of the large binary GLBs.
"""
import argparse,json
from pathlib import Path
from emerald_v5_anatomical_census import PINNED, RISK_PAIRS, DONOR_SHA
from emerald_v5_expanded_broadphase import AUDITOR_SHA, SAMPLES, MARGIN

ROOT=Path(__file__).resolve().parents[1]
RECEIPT=ROOT/"assets/emerald/evolution-v5/expanded-sampled-bounds.json"
STAGES=("pathfinder","archivist")
EXPECTED_STATE_ROWS=(
 "OOOEOOOOSOSOSOOOOSO","OOOEOOOOSOSOSOOOOSO","OOOEOOOOSOSOSOOOOSO",
 "OOOEOOOOSOSOSOOOOSO","SOOEOSSOOOOSOOOOOSO","SOOEOOSOSSSSSOOOOSO",
 "SOOEOOSSSSSSSOOOOSO",
 "OOOEOOOOSOSOSOOOOSO","OOOEOOOOSOSOSOOOOSO","OOOEOOOOSOSOSOOOOSO",
 "OOOEOOOOOOSOSOOOOSO","SOOEOSSOOOOSOOOOOSO","SOOEOOSOSSSSSOOOOSO",
 "SOOEOSSSSSSSSOOOOSO",
)

def require(x,reason):
 if not x:raise ValueError(reason)

def verify(r):
 require(r.get("schema")=="skeleton.emerald.expanded-anatomy-bounds-summary.v1"
         and r.get("reviewed_contact_tool_sha256")==AUDITOR_SHA
         and r.get("margin_m")==MARGIN
         and r.get("group_count")==11
         and r.get("anatomical_pairs")==len(RISK_PAIRS)==19
         and r.get("pose_count")==14,"wrong original source, margin or pair policy")
 originals=r.get("model_sources")
 require(isinstance(originals,list) and len(originals)==2,"missing original models")
 for model,stage in zip(originals,STAGES):
  require(model.get("stage")==stage and
          (model.get("bytes"),model.get("sha256"))==PINNED[stage,"v5"],
          "actual exported model SHA differs")
 poses=r.get("compressed_pair_states")
 require(isinstance(poses,list) and len(poses)==14,"missing exported pose evidence")
 tally={"S":0,"O":0,"E":0}
 for i,row in enumerate(poses):
  stage=STAGES[i//7];clip,frac=SAMPLES[i%7]
  require(row.get("stage")==stage and row.get("clip")==clip and
          row.get("fraction")==frac,"duplicate, reordered or missing sampled pose")
  code=row.get("codes","")
  require(type(code) is str and len(code)==19 and
          code==EXPECTED_STATE_ROWS[i] and set(code)<=set("SOE"),
          "source-bound pair evidence changed")
  require(code[3]=="E" and code.count("E")==1,
          "empty anatomical cohort incorrectly treated as cleared")
  for c in code:tally[c]+=1
 require(tally=={"S":76,"O":176,"E":14} and r.get("summary")=={
          "sampled_separated":76,"overlapping_needs_triangle_test":176,
          "empty_unqualified":14},"truncated or inflated broadphase report")
 require(all(r.get(flag) is False for flag in (
     "all_intervals_qualified","full_triangle_narrowphase_completed",
     "continuous_collision_qualified","equipment_enabled",
     "artist_approved","physical_rtx_verified","release_qualified")),
     "attempt to certify unknown collision or release evidence")
 return {"schema":"skeleton.emerald.aabb-evidence-consistency.v1",
         "recorded_actual_model_shas_match":True,
         "sampled_pose_count":14,"anatomical_pair_instances":266,
         "sampled_separated_at_instants":76,"overlap_unresolved":176,
         "empty_group_unresolved":14,
         "models_replayed_by_source_only_ci":False,
         "continuous_collision_qualified":False,
         "artist_approved":False,"release_qualified":False}

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,default=RECEIPT)
 args=p.parse_args()
 print(json.dumps(verify(json.loads(args.receipt.read_bytes())),indent=2))
