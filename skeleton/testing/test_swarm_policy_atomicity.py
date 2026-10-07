import pytest

from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota


def test_invalid_weight_does_not_partially_commit_quota_policy() -> None:
    governor = SwarmIngressGovernor()
    original = governor.quota.limit("tenant")
    replacement = Quota(max_queued=7, max_leased=3, max_payload_bytes=700)

    with pytest.raises(ValueError, match="positive integer"):
        governor.configure_tenant("tenant", quota=replacement, weight=float("nan"))

    assert governor.quota.limit("tenant") == original
    assert "tenant" not in governor.fairness.snapshot()


def test_valid_combined_policy_configuration_commits_both_dimensions() -> None:
    governor = SwarmIngressGovernor()
    quota = Quota(max_queued=9, max_leased=4, max_payload_bytes=900)

    governor.configure_tenant("tenant", quota=quota, weight=5)

    assert governor.quota.limit("tenant") == quota
    assert governor.fairness.snapshot()["tenant"]["weight"] == 5
