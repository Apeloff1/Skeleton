from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import build_operations_dashboard
from skeleton.ai.runtime.deferred.operations_experience import DashboardMetric, DashboardProjection

def test_operations_dashboard_filters_stale_metrics_and_binds_runbooks()->None:
    evidence=build_operations_dashboard(
        DashboardProjection(max_age_seconds=10),
        (
            DashboardMetric("fresh",1.0,"count",95),
            DashboardMetric("stale",2.0,"count",80),
        ),
        now=100,runbook_refs=("runbook://fresh",),
    )
    assert evidence.metric_ids==("fresh",)
    assert evidence.stale_metric_ids==("stale",)
    assert evidence.runbook_refs==("runbook://fresh",)
    assert evidence.production_authority is False
