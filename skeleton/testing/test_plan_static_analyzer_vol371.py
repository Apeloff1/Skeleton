from skeleton.ai.plan_static_analysis import *
def test_findings_have_location_severity_remediation():
 r=analyze("v1",({"id":"a","privileged":True},),());d=r.diagnostics[0];assert (d.location,d.severity,d.remediation)
def test_analysis_is_deterministic():assert analyze("v1",({"id":"a"},),())==analyze("v1",({"id":"a"},),())
