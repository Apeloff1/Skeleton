from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    EnterpriseTopology, assess_enterprise_topology,
)

def test_enterprise_topology_requires_sso_audit_backup_residency_and_replicas()->None:
    topology=EnterpriseTopology("ha",("eu-a","eu-b"),2)
    accepted=assess_enterprise_topology(
        topology,replica_count=2,sso_verified=True,audit_verified=True,
        backup_verified=True,residency_verified=True,
    )
    assert accepted.accepted is True
    assert accepted.blockers==()
    assert accepted.production_authority is False

    blocked=assess_enterprise_topology(
        topology,replica_count=1,sso_verified=False,audit_verified=False,
        backup_verified=False,residency_verified=False,
    )
    assert blocked.accepted is False
    assert blocked.blockers==(
        "audit-unverified","backup-unverified","replica-count-below-topology",
        "residency-unverified","sso-unverified",
    )
