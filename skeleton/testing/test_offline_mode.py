from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.component_provider_assurance import (
    ComponentProviderAssuranceError,
    OfflineCapability,
    evaluate_offline_capabilities,
)
from skeleton.ai.runtime.deferred.research_evaluation import DeploymentProfile

def test_offline_capability_map_uses_local_model_and_storage_without_network()->None:
    profile=DeploymentProfile("offline","offline","local_only","device")
    decision=evaluate_offline_capabilities(
        profile,
        (
            OfflineCapability("chat",True,True,False),
            OfflineCapability("cloud-search",False,False,True),
            OfflineCapability("history",False,True,False,"memory-only"),
        ),
        local_model_present=True,local_storage_present=True,
    )
    assert decision.available_capabilities==("chat","history")
    assert decision.unavailable_capabilities==("cloud-search",)
    assert decision.network_access is False
    assert decision.production_authority is False

def test_offline_mode_rejects_nonoffline_profile()->None:
    with pytest.raises(ComponentProviderAssuranceError,match="offline profile"):
        evaluate_offline_capabilities(
            DeploymentProfile("online","online","hosted","cloud"),
            (OfflineCapability("chat",False,False,False),),
            local_model_present=False,local_storage_present=False,
        )
