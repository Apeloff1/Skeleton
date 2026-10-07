#!/usr/bin/env python3
"""Produce a deterministic dry-run accountability reconstruction plan.

This never mutates the canonical ledger. It classifies what repository history
allows a later materializer to restore and what must remain blocked.
"""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"machine/accountability_recovery_evidence.json"
OUT=ROOT/"machine/accountability_reconstruction_plan.json"

def main():
 d=json.loads(SRC.read_text(encoding="utf-8")); records={}
 def rec(rid): return records.setdefault(rid,{"record_id":rid,"recoverable":[],"blocked":["verification_signoff","completion"],"sources":[]})
 for a in d.get("anchors",[]):
  claim=a.get("claim",""); gran=a.get("recovery_granularity","")
  for rid in a.get("record_ids",[]):
   r=rec(rid); r["sources"].append(a["source_commit"])
   if "implementation" in claim.lower() or gran.startswith("implementation_signoff"):
    r["recoverable"].append("implementation_signoff_presence")
   if "independent" in claim.lower() and ("completion" in claim.lower() or "verified" in claim.lower()):
    r["recoverable"].append("verification_evidence_anchor")
   if a.get("verification_state")=="explicitly_unsigned": r["blocked"].append("verification_promotion_from_this_anchor")
 for c in d.get("cohorts",[]):
  if c.get("name")!="terminal_p1_retro_sign": continue
  for rid in c.get("membership_derivation",{}).get("derived_record_ids",[]):
   r=rec(rid); r["sources"].append(c["source_commit"]); r["recoverable"].append("implementation_signoff_presence")
 for r in records.values():
  r["recoverable"]=sorted(set(r["recoverable"]));r["blocked"]=sorted(set(r["blocked"]));r["sources"]=sorted(set(r["sources"]))
 out={"schema_version":1,"mode":"dry_run_only","authority":"non_mutating_reconstruction_plan","source":"machine/accountability_recovery_evidence.json","record_count":len(records),"records":[records[k] for k in sorted(records)]}
 OUT.write_text(json.dumps(out,indent=2)+"\\n",encoding="utf-8");print(f"planned {len(records)} recoverable accountability records")
if __name__=="__main__": main()
