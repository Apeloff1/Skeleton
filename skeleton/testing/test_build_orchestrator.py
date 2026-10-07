from skeleton.automation.build_orchestrator import decide
def test_retryable_ci_failure_repairs():assert decide(campaign_status="continue",build_status="continue",ci_complete=True,failed_gates=("Backend Quality",),fresh_supervisor=True,operator_hold=False).action=="repair"
def test_security_ci_failure_quarantines():assert decide(campaign_status="continue",build_status="continue",ci_complete=True,failed_gates=("Workflow Input Security",),fresh_supervisor=True,operator_hold=False).action=="quarantine"
def test_completion_waits_for_ci():assert decide(campaign_status="complete",build_status="complete",ci_complete=False,failed_gates=(),fresh_supervisor=True,operator_hold=False).action=="wait_ci"
