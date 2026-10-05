from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.component_provider_assurance import (
    ComponentProviderAssuranceError,
    assess_dependency_health,
)
from skeleton.ai.runtime.deferred.operations_experience import DependencyHealth

A="a"*64

def test_healthy_dependency_binds_sbom_without_backlog()->None:
    evidence=assess_dependency_health(
        DependencyHealth("lib","1.0",0,False,True),sbom_digest=A,
    )
    assert evidence.healthy is True
    assert evidence.backlog_ref is None
    assert evidence.blocker_codes==()

def test_unhealthy_dependency_requires_backlog_and_exposes_reasons()->None:
    dependency=DependencyHealth("lib","0.9",2,True,False)
    with pytest.raises(ComponentProviderAssuranceError,match="backlog"):
        assess_dependency_health(dependency,sbom_digest=A)
    evidence=assess_dependency_health(
        dependency,sbom_digest=A,backlog_ref="BACKLOG-DEP-1",
    )
    assert evidence.healthy is False
    assert evidence.blocker_codes==("known-vulnerability","stale","unsupported")
    assert evidence.backlog_ref=="BACKLOG-DEP-1"
