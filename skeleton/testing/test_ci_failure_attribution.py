from skeleton.automation.ci_failure_attribution import attribute
def test_security_failure_quarantines():assert attribute("Workflow Input Security").action=="quarantine"
def test_quality_failure_repairs():assert attribute("Backend Quality").action=="repair"
def test_unknown_does_not_auto_repair():assert not attribute("Mystery Gate").retryable
