from __future__ import annotations
import pytest
from skeleton.ai.evaluation.contamination_auditor import ContentFingerprint,ContaminationAudit,ContaminationAuditError,audit_contamination,fingerprint_text

def test_normalization_fingerprint_is_whitespace_and_case_stable():
    assert fingerprint_text("Hello   World")==fingerprint_text(" hello world ")

def test_exact_train_eval_overlap_is_reported():
    items=(
        ContentFingerprint.from_text("train-1","train","same content"),
        ContentFingerprint.from_text("test-1","test","SAME   CONTENT"),
        ContentFingerprint.from_text("test-2","test","different"),
    )
    audit=audit_contamination(audit_id="audit",items=items)
    assert audit.clean is False
    assert len(audit.findings)==1
    assert audit.findings[0].training_item_id=="train-1"
    assert audit.sota_claim_allowed is False

def test_clean_audit_contains_no_findings():
    audit=audit_contamination(
        audit_id="clean",
        items=(ContentFingerprint.from_text("train","train","alpha"),ContentFingerprint.from_text("test","benchmark","beta")),
    )
    assert audit.clean is True

def test_audit_cannot_authorize_sota_claim():
    with pytest.raises(ContaminationAuditError,match="cannot authorize"):
        ContaminationAudit("a",(),True,True)
