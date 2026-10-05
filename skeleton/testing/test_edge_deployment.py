from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    EdgeResourceTier, qualify_edge_deployment,
)
from skeleton.ai.runtime.deferred.research_evaluation import DeploymentProfile

A="a"*64

def test_edge_deployment_binds_resource_tier_and_router_constraints()->None:
    evidence=qualify_edge_deployment(
        DeploymentProfile("edge","offline","local_only","device"),
        EdgeResourceTier("small",2_000,4_000,4096,("local-router",)),
        model_digest=A,model_bytes=1_000,memory_bytes=2_000,
        context_tokens=2048,router_class="local-router",local_storage_present=True,
    )
    assert evidence.eligible is True
    assert evidence.blockers==()
    assert evidence.production_authority is False

def test_edge_deployment_exposes_all_resource_blockers()->None:
    evidence=qualify_edge_deployment(
        DeploymentProfile("edge","offline","local_only","device"),
        EdgeResourceTier("small",100,100,100,("allowed",)),
        model_digest=A,model_bytes=101,memory_bytes=101,
        context_tokens=101,router_class="other",local_storage_present=False,
    )
    assert evidence.eligible is False
    assert evidence.blockers==(
        "context-exceeded","local-storage-missing","memory-exceeded",
        "model-size-exceeded","router-class-unsupported",
    )
