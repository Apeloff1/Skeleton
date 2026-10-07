from skeleton.ai.plan_static_analysis import *
def test_findings_have_location_severity_remediation():
 r=analyze("v1",({"id":"a","privileged":True},),());d=r.diagnostics[0];assert (d.location,d.severity,d.remediation)
def test_analysis_is_deterministic():assert analyze("v1",({"id":"a"},),())==analyze("v1",({"id":"a"},),())

def test_rule_severity_is_applied():assert analyze("v",({"id":"a"},{"id":"a"}),(PlanLintRule("duplicate-step","warning"),)).diagnostics[0].severity=="warning"
def test_malformed_step_becomes_diagnostic():assert analyze("v",({},),()).diagnostics[0].rule_id=="malformed-step"

def test_invalid_rule_severity_rejected():
 import pytest
 with pytest.raises(ValueError):analyze("v",(),(PlanLintRule("x","fatalish"),))
