#!/usr/bin/env python3
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; EXPECTED=("VOL-143","VOL-144","VOL-145","VOL-146","VOL-147","VOL-148","VOL-149")
TESTS={"VOL-143":"skeleton/testing/test_training_control_plane.py","VOL-144":"skeleton/testing/test_distributed_training.py","VOL-145":"skeleton/testing/test_training_checkpointing.py","VOL-146":"skeleton/testing/test_elastic_training_recovery.py","VOL-147":"skeleton/testing/test_training_observability.py","VOL-148":"skeleton/testing/test_training_eval_gates.py","VOL-149":"skeleton/testing/test_post_training_lab.py"}; MODULES={"VOL-143":"skeleton/learning/training_control.py","VOL-144":"skeleton/learning/distributed_training.py","VOL-145":"skeleton/learning/training_checkpointing.py","VOL-146":"skeleton/learning/elastic_training.py","VOL-147":"skeleton/learning/training_observability.py","VOL-148":"skeleton/learning/training_eval_gates.py","VOL-149":"skeleton/learning/post_training_lab.py"}
class TrainingCandidateError(RuntimeError): pass
def load(root,p):
 try:return json.loads((root/p).read_text())
 except Exception as exc: raise TrainingCandidateError(f"cannot read {p}") from exc
def validate(root=ROOT,head=None):
 root=Path(root).resolve(); f=load(root,"machine/ai_masterplan_continuation_frontier.json"); m=load(root,"machine/ai_master_plan.json"); t=load(root,"machine/ai_file_tree.json"); d=load(root,"machine/ai_p3t2_data_candidate.json"); c=load(root,"machine/ai_p3t2_training_candidate.json")
 if d.get("status")!="implementation_candidate" or c.get("status")!="implementation_candidate": raise TrainingCandidateError("dependency status drift")
 owner=next((x for x in f["next_tranche"]["planned_task_owners"] if x.get("task_id")=="P3T2-TRAINING-01"),None)
 if owner is None or owner.get("depends_on")!=["P3T2-DATA-01"] or tuple(owner.get("primary_volume_refs",()))!=EXPECTED or tuple(c.get("volume_refs",()))!=EXPECTED: raise TrainingCandidateError("owner/dependency drift")
 if any(owner.get(k) is not False or c["promotion_state"].get(k) is not False for k in ("completion_checkbox","implementation_signed","verification_signed")) or c["promotion_state"].get("may_self_close") is not False: raise TrainingCandidateError("illegal promotion")
 vols={v.get("key"):v for v in m["volumes"]}
 for key in EXPECTED:
  v=vols[key]; module=MODULES[key]; test=TESTS[key]
  if v.get("completion_checkbox") is not False or v.get("implementation_status")=="verified": raise TrainingCandidateError(f"{key} completion drift")
  if module not in v.get("implementation_paths",[]) or test not in v.get("tests",[]) or f"planned:{test}" in v.get("tests",[]): raise TrainingCandidateError(f"{key} implementation/test drift")
 mapping=next((x for x in t["mappings"] if x.get("id")=="AIFT-LEARNING"),None)
 if mapping is None or not set(EXPECTED).issubset(set(mapping.get("volume_refs",[]))): raise TrainingCandidateError("AIFT-LEARNING volume drift")
 for left,right in c["mirror_pairs"]:
  if (root/left).read_bytes()!=(root/right).read_bytes(): raise TrainingCandidateError(f"mirror drift: {left}")
 if head is not None and re.fullmatch(r"[0-9a-f]{40}",head) is None: raise TrainingCandidateError("invalid exact head")
 return {"status":"valid","task_id":"P3T2-TRAINING-01","volume_count":7,"test_count":7,"mirror_count":7,"completion_checkbox":False,"reported_head":head}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--head"); p.add_argument("--json",action="store_true"); a=p.parse_args()
 try:r=validate(ROOT,head=a.head)
 except TrainingCandidateError as exc: print(f"P3-T2 training candidate: FAIL: {exc}",file=sys.stderr); return 1
 print(json.dumps(r,indent=2,sort_keys=True) if a.json else "P3-T2 training candidate: OK"); return 0
if __name__=="__main__": raise SystemExit(main())
