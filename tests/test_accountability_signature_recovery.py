import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def data(): return json.loads((ROOT/"machine/accountability_signature_recovery.json").read_text())
def test_signature_recovery_is_conservative_and_non_authorizing():
 d=data();assert d["authority"]=="recovery_strength_classification_only";assert d["record_count"]==26;assert d["signature_fields_recoverable_count"]==16;assert d["evidence_only_manual_review_count"]==10
 assert all(r["automatic_signature_write_authorized"] is False for r in d["records"])
def test_only_fully_structured_records_are_signature_recoverable():
 d=data();rich={r["record_id"] for r in d["records"] if r["classification"]=="signature_fields_recoverable"}
 assert rich==['ACC-AIQ-S0-COST-01','ACC-AIQ-S0-GOV-01','ACC-AIQ-S0-GOV-02','ACC-AIQ-S0-GOV-03','ACC-AIQ-S0-STATE-01','ACC-AIQ-S0-STATE-02','ACC-VOL-013','ACC-VOL-014','ACC-VOL-015','ACC-VOL-016','ACC-VOL-017','ACC-VOL-056','ACC-VOL-057','ACC-VOL-059','ACC-VOL-248','ACC-VOL-253']
 for r in d["records"]:
  if r["classification"]=="signature_fields_recoverable": assert r["verifier_identity_recovered"] and r["exact_head_recovered"] and r["run_or_job_evidence_recovered"] and r["completion_semantics_recovered"]
