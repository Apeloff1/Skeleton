import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def data(): return json.loads((ROOT/"machine/accountability_signature_recovery.json").read_text())
def test_signature_recovery_is_conservative_and_non_authorizing():
 d=data();assert d["authority"]=="recovery_strength_classification_only";assert d["record_count"]==25;assert d["signature_fields_recoverable_count"]==5;assert d["evidence_only_manual_review_count"]==20
 assert all(r["automatic_signature_write_authorized"] is False for r in d["records"])
def test_only_fully_structured_records_are_signature_recoverable():
 d=data();rich={r["record_id"] for r in d["records"] if r["classification"]=="signature_fields_recoverable"}
 assert rich=={"ACC-VOL-015","ACC-VOL-016","ACC-VOL-056","ACC-VOL-057","ACC-VOL-059"}
 for r in d["records"]:
  if r["classification"]=="signature_fields_recoverable": assert r["verifier_identity_recovered"] and r["exact_head_recovered"] and r["run_or_job_evidence_recovered"] and r["completion_semantics_recovered"]
