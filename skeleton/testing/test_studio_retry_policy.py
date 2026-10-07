import pytest
from skeleton.automation.studio_retry_policy import decide
def test_validation_failure_repairs_then_quarantines():
 assert decide(attempt=1,validation_failed=True,structural_failure=False).action=="repair"
 assert decide(attempt=3,validation_failed=True,structural_failure=False).action=="quarantine"
def test_structural_failure_never_repairs():
 assert decide(attempt=0,validation_failed=True,structural_failure=True).action=="reject"
def test_negative_attempt_rejected():
 with pytest.raises(ValueError): decide(attempt=-1,validation_failed=True,structural_failure=False)
