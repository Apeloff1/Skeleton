#!/usr/bin/env python3
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; EXPECTED=("VOL-137","VOL-138","VOL-139","VOL-140","VOL-141","VOL-142")
TESTS={"VOL-137":"skeleton/testing/test_data_ingestion.py","VOL-138":"skeleton/testing/test_document_intelligence.py","VOL-139":"skeleton/testing/test_data_lineage.py","VOL-140":"skeleton/testing/test_data_quality.py","VOL-141":"skeleton/testing/test_dataset_registry.py","VOL-142":"skeleton/testing/test_synthetic_data_factory.py"}; MODULES={"VOL-137":"skeleton/data/ingestion.py","VOL-138":"skeleton/data/document_intelligence.py","VOL-139":"skeleton/data/lineage_governance.py","VOL-140":"skeleton/data/quality.py","VOL-141":"skeleton/data/dataset_registry.py","VOL-142":"skeleton/data/synthetic.py"}
class DataCandidateError(RuntimeError): pass
def load(root,p):
 try:v=json.loads((root/p).read_text())
 except Exception as exc: raise DataCandidateError(f"cannot read {p}") from exc
 return v
def validate(root=ROOT,head=None):
 root=Path(root).resolve(); f=load(root,"machine/ai_masterplan_continuation_frontier.json"); m=load(root,"machine/ai_master_plan.json"); t=load(root,"machine/ai_file_tree.json"); s=load(root,"machine/ai_p3t2_storage_candidate.json"); c=load(root,"machine/ai_p3t2_data_candidate.json")
 if c.get("status")!="implementation_candidate" or s.get("status")!="implementation_candidate": raise DataCandidateError("candidate status drift")
 owner=next((x for x in f["next_tranche"]["planned_task_owners"] if x.get("task_id")=="P3T2-DATA-01"),None)
 if owner is None or owner.get("depends_on")!=["P3T2-STORAGE-01"] or tuple(owner.get("primary_volume_refs",()))!=EXPECTED or tuple(c.get("volume_refs",()))!=EXPECTED: raise DataCandidateError("owner/dependency drift")
 if any(owner.get(k) is not False or c["promotion_state"].get(k) is not False for k in ("completion_checkbox","implementation_signed","verification_signed")) or c["promotion_state"].get("may_self_close") is not False: raise DataCandidateError("illegal promotion")
 vols={v.get("key"):v for v in m["volumes"]}
 for key in EXPECTED:
  v=vols[key]; module=MODULES[key]; test=TESTS[key]
  if v.get("completion_checkbox") is not False or v.get("implementation_status")=="verified": raise DataCandidateError(f"{key} completion drift")
  if module not in v.get("implementation_paths",[]) or test not in v.get("tests",[]) or f"planned:{test}" in v.get("tests",[]): raise DataCandidateError(f"{key} implementation/test drift")
 mapping=next((x for x in t["mappings"] if x.get("id")=="AIFT-DATA"),None)
 if mapping is None or not set(EXPECTED).issubset(set(mapping.get("volume_refs",[]))): raise DataCandidateError("AIFT-DATA volume drift")
 for left,right in c["mirror_pairs"]:
  if (root/left).read_bytes()!=(root/right).read_bytes(): raise DataCandidateError(f"mirror drift: {left}")
 if head is not None and re.fullmatch(r"[0-9a-f]{40}",head) is None: raise DataCandidateError("invalid exact head")
 return {"status":"valid","task_id":"P3T2-DATA-01","volume_count":6,"test_count":6,"mirror_count":6,"completion_checkbox":False,"reported_head":head}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--head"); p.add_argument("--json",action="store_true"); a=p.parse_args()
 try:r=validate(ROOT,head=a.head)
 except DataCandidateError as exc: print(f"P3-T2 data candidate: FAIL: {exc}",file=sys.stderr); return 1
 print(json.dumps(r,indent=2,sort_keys=True) if a.json else "P3-T2 data candidate: OK"); return 0
if __name__=="__main__": raise SystemExit(main())
