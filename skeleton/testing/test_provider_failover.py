from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.component_provider_assurance import (
    ComponentProviderAssuranceError,
    choose_provider_failover,
)
from skeleton.ai.runtime.deferred.research_evaluation import ProviderRisk

def providers():
    return (
        ProviderRisk("provider-a",0.3,("public",),("eu",),True),
        ProviderRisk("provider-b",0.1,("public",),("eu","us"),True),
    )

def test_failover_selects_lowest_risk_policy_compatible_provider()->None:
    decision=choose_provider_failover(
        providers(),required_data_class="public",allowed_regions=("eu",),
        max_risk=0.5,
        compatibility_classes={"provider-a":"text-v1","provider-b":"text-v1"},
    )
    assert decision.selected_provider_id=="provider-b"
    assert decision.compatibility_class=="text-v1"
    assert decision.production_authority is False

def test_failover_requires_exact_compatibility_inventory()->None:
    with pytest.raises(ComponentProviderAssuranceError,match="exact provider inventory"):
        choose_provider_failover(
            providers(),required_data_class="public",allowed_regions=("eu",),
            max_risk=0.5,compatibility_classes={"provider-a":"text-v1"},
        )
