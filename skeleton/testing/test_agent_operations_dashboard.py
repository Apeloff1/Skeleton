from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    AgentOpsRecord, DeploymentOperationsAssuranceError, build_agent_ops_projection,
)

A="a"*64
B="b"*64

def test_agent_ops_projection_binds_human_control_receipt()->None:
    projection=build_agent_ops_projection(
        (
            AgentOpsRecord("agent-a","task-a","running",A,None),
            AgentOpsRecord("agent-b","task-b","paused",A,B),
        )
    )
    assert len(projection.records)==2
    assert len(projection.projection_digest)==64

def test_human_controlled_agent_state_requires_receipt()->None:
    with pytest.raises(DeploymentOperationsAssuranceError,match="control receipt"):
        AgentOpsRecord("agent","task","stopped",A,None)
