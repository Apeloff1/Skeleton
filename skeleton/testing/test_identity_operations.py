import pytest
from skeleton.ai.runtime.deferred.identity_operations import (
 FederationConfig,IdentityClaim,map_identity,AdminPolicy,AdminAction,authorize_admin,
 AuditEntry,AuditQuery,project_audit,OpsMetric,OpsAlert,OperationsDashboard,TelemetryState,
 AgentControlAction,project_agent_ops,
)

def test_federation_fails_closed_on_issuer_audience_key_and_revocation():
 c=FederationConfig("issuer",("app",),("k1",))
 good=IdentityClaim("issuer","app","stable-sub","k1",("ops",),"s1")
 assert map_identity(c,good).subject=="stable-sub"
 for bad in [
  IdentityClaim("evil","app","s","k1",(),"s"),
  IdentityClaim("issuer","other","s","k1",(),"s"),
  IdentityClaim("issuer","app","s","bad",(),"s"),
  IdentityClaim("issuer","app","s","k1",(),"s",True),
 ]:
  with pytest.raises(PermissionError): map_identity(c,bad)

def test_mutable_display_claim_cannot_be_durable_identity():
 with pytest.raises(ValueError,match="mutable"): FederationConfig("i",("a",),("k",),"email")

def test_admin_rejects_model_generated_privileged_action():
 p=AdminPolicy(("rotate_key",),())
 a=AdminAction("a","human","rotate_key","digest","auth",model_generated=True)
 assert not authorize_admin(p,a).accepted

def test_break_glass_requires_separate_approval():
 p=AdminPolicy(("shutdown",),("shutdown",))
 a=AdminAction("a","human","shutdown","digest","auth")
 assert not authorize_admin(p,a).accepted
 assert authorize_admin(p,AdminAction("a","human","shutdown","digest","auth",False,"approval")).accepted

def test_audit_projection_is_tenant_scoped_and_redacted():
 entries=(AuditEntry("1","t1","c","r","token=SECRET",("SECRET",)),AuditEntry("2","t2","c","r2","other"),)
 view=project_audit(entries,AuditQuery("t1"))
 assert len(view.entries)==1
 assert view.entries[0].summary=="token=[REDACTED]"
 assert view.entries[0].secret_fields==()

def test_audit_correlation_filter_does_not_cross_tenant():
 entries=(AuditEntry("1","t1","a","r","one"),AuditEntry("2","t1","b","r","two"))
 assert [e.entry_id for e in project_audit(entries,AuditQuery("t1","b")).entries]==["2"]

def test_dashboard_never_reports_green_for_stale_or_unknown_telemetry():
 for state in (TelemetryState.STALE,TelemetryState.UNKNOWN):
  d=OperationsDashboard((OpsMetric("slo",1.0,state,"t"),),())
  assert not d.healthy

def test_dashboard_hard_blocker_dominates_fresh_metrics():
 d=OperationsDashboard((OpsMetric("slo",1.0,TelemetryState.FRESH,"t"),),(OpsAlert("incident","critical",True,"runbook"),))
 assert not d.healthy

def test_agent_projection_surfaces_orphan_and_budget_exhaustion():
 v=project_agent_ops("worker-1","t",0,lease_stale=True)
 assert {a.kind for a in v.alerts}=={"stale_or_orphan_lease","budget_exhausted"}
 assert all(a.blocker for a in v.alerts)

def test_agent_human_control_requires_governed_api_receipt():
 with pytest.raises(ValueError,match="governed_api_receipt"):
  AgentControlAction("worker-1","stop","operator","")
