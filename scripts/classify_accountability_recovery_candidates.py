#!/usr/bin/env python3
"""Classify accountability recovery records for later evidence-bound promotion.

Candidate means evidence exists to review; it never means signed or complete.
"""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"machine/accountability_reconstruction_plan.json"
OUT=ROOT/"machine/accountability_recovery_candidates.json"
def main():
 p=json.loads(PLAN.read_text())
 rows=[]
 for r in p["records"]:
  has_impl="implementation_signoff_presence" in r["recoverable"]
  has_verify="verification_evidence_anchor" in r["recoverable"]
  state="independent_evidence_review_candidate" if has_verify else "implementation_only_blocked"
  rows.append({"record_id":r["record_id"],"state":state,"implementation_evidence_recovered":has_impl,"independent_evidence_anchor_recovered":has_verify,"verification_signature_authorized":False,"completion_authorized":False,"sources":r["sources"]})
 out={"schema_version":1,"authority":"candidate_classification_only","record_count":len(rows),"independent_evidence_candidate_count":sum(x["state"]=="independent_evidence_review_candidate" for x in rows),"implementation_only_blocked_count":sum(x["state"]=="implementation_only_blocked" for x in rows),"records":rows}
 OUT.write_text(json.dumps(out,indent=2)+"\\n");print(json.dumps({k:out[k] for k in ("record_count","independent_evidence_candidate_count","implementation_only_blocked_count")}))
if __name__=="__main__":main()
