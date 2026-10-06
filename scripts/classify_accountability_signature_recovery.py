#!/usr/bin/env python3
"""Refine independent-evidence candidates by reconstruction strength."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"machine/accountability_recovery_evidence.json";OUT=ROOT/"machine/accountability_signature_recovery.json"
def main():
 d=json.loads(E.read_text());rows=[]
 for a in d.get("anchors",[]):
  claim=a.get("claim","").lower()
  if "independent" not in claim: continue
  exact=a.get("exact_head") or a.get("evidence_head")
  runs=a.get("verification") or a.get("verification_runs") or a.get("corroborating_runs")
  verifier=a.get("verification_signer")
  completed=a.get("completed_at_utc")
  explicit_completion="completion" in claim and "completion remains separate" not in claim
  rich=bool(verifier and exact and runs and completed and explicit_completion)
  for rid in a.get("record_ids",[]):
   rows.append({"record_id":rid,"classification":"signature_fields_recoverable" if rich else "evidence_only_manual_review","source_commit":a["source_commit"],"verifier_identity_recovered":bool(verifier),"exact_head_recovered":bool(exact),"run_or_job_evidence_recovered":bool(runs),"completion_semantics_recovered":bool(completed and explicit_completion),"automatic_signature_write_authorized":False})
 out={"schema_version":1,"authority":"recovery_strength_classification_only","record_count":len(rows),"signature_fields_recoverable_count":sum(x["classification"]=="signature_fields_recoverable" for x in rows),"evidence_only_manual_review_count":sum(x["classification"]=="evidence_only_manual_review" for x in rows),"records":sorted(rows,key=lambda x:x["record_id"])}
 OUT.write_text(json.dumps(out,indent=2)+"\\n");print(json.dumps({k:out[k] for k in ("record_count","signature_fields_recoverable_count","evidence_only_manual_review_count")}))
if __name__=="__main__":main()
