#!/usr/bin/env python3
"""Fail-closed recovery for an empty AI accountability ledger.

Reconstructs only unsigned baseline records from canonical mirrors. It never
manufactures signatures, timestamps, history, completion, or evidence. If a
mirror claims signed/completed state that cannot be recovered from an existing
ledger, reconstruction aborts and requires historical evidence recovery.
"""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load(name): return json.loads((ROOT/name).read_text(encoding="utf-8"))
def unsigned(): return {"signed":False,"signer_id":None,"signer_type":None,"role":None,"signed_at_utc":None,"git_sha":None,"evidence_refs":[],"statement":None,"signature_method":None,"signature_ref":None}
def record(rid,typ,title,status,checked=False):
 if checked or status.lower() not in {"planned","unverified"}:
  raise RuntimeError(f"{rid}: refusing to reconstruct non-baseline accountability without signed history")
 return {"id":rid,"type":typ,"title":title,"baseline_status":status,"status":status,"signing_required":True,"checkbox":False,"checkbox_mark":"[ ]","started_at_utc":None,"completed_at_utc":None,"last_event_at_utc":None,"implementation_signoff":unsigned(),"verification_signoff":unsigned(),"independence_exception":None,"evidence":[],"history":[]}
def build():
 master=load("machine/ai_master_plan.json");queue=load("machine/ai_build_queue.json");p1=load("machine/ai_p1_task_backlog.json");catalog=load("machine/ai_edge_case_catalog.json")
 records=[]
 for v in master["volumes"]: records.append(record(f"ACC-{v['key']}","volume",v["title"],v["implementation_status"],v["completion_checkbox"]))
 for i,wp in enumerate(master["p0_work_packages"]): records.append(record(f"ACC-WP-W{i:02d}","work_package",wp.get("title",f"Work Package W{i:02d}"),wp.get("implementation_status","unverified"),wp.get("completion_checkbox",False)))
 for t in queue["tasks"]: records.append(record(f"ACC-{t['task_id']}","queue_task",t.get("objective",t["task_id"]),t["status"],t["completion_checkbox"]))
 for t in p1["tasks"]: records.append(record(t["accountability_ref"],"p1_task",t["title"],t["accountability_status"],t["completion_checkbox"]))
 for vs in master["vertical_slices"]: records.append(record(f"ACC-{vs}","vertical_slice",str(vs),"unverified",False))
 for e in catalog["entries"]: records.append(record(f"ACC-{e['id']}","catalog_entry",e["title"],e.get("accountability_status","planned"),e["completion_checkbox"]))
 return {"schema_version":1,"tracked_counts":{"volumes":len(master["volumes"]),"work_packages":31,"queue_tasks":len(queue["tasks"]),"p1_tasks":len(p1["tasks"]),"vertical_slices":len(master["vertical_slices"]),"catalog_entries":len(catalog["entries"]),"total":len(records)},"records":records}
def main():
 ledger=ROOT/"machine/ai_build_accountability.json"
 if ledger.read_text(encoding="utf-8").strip(): raise SystemExit("refusing to overwrite non-empty accountability ledger")
 try:data=build()
 except RuntimeError as e: raise SystemExit(f"ACCOUNTABILITY RECOVERY BLOCKED: {e}")
 ledger.write_text(json.dumps(data,indent=2)+"\\n",encoding="utf-8")
 print(f"reconstructed {len(data['records'])} unsigned baseline records")
if __name__=="__main__": main()
