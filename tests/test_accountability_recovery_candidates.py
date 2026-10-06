import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def data(): return json.loads((ROOT/"machine/accountability_recovery_candidates.json").read_text())
def test_candidate_classification_is_non_authorizing():
 d=data();assert d["authority"]=="candidate_classification_only";assert d["record_count"]==170;assert d["independent_evidence_candidate_count"]==26;assert d["implementation_only_blocked_count"]==144
 assert all(r["verification_signature_authorized"] is False and r["completion_authorized"] is False for r in d["records"])
def test_candidate_partition_is_total_and_unique():
 d=data();ids=[r["record_id"] for r in d["records"]];assert len(ids)==len(set(ids))==170
 assert {r["state"] for r in d["records"]} <= {"independent_evidence_review_candidate","implementation_only_blocked"}
 assert sum(r["state"]=="independent_evidence_review_candidate" for r in d["records"])==26
