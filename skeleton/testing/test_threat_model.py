from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.contracts import SecurityContractError
from skeleton.ai.runtime.security.threat_model import (
    Threat,
    ThreatImpactTrigger,
    ThreatModel,
    canonical_vol026_threat_model,
)


def test_canonical_threat_model_maps_required_assets_to_validation() -> None:
    model=canonical_vol026_threat_model()
    assert {threat.asset for threat in model.threats} == {
        "tool-authority",
        "secrets",
        "filesystem",
        "network-egress",
        "supply-chain",
    }
    assert all(threat.validation for threat in model.threats)
    assert len(model.digest)==64


def test_boundary_changes_trigger_threat_model_review() -> None:
    model=canonical_vol026_threat_model()
    assert model.review_required(("authority",)) is True
    assert model.review_required(("network",)) is True
    assert model.review_required(("storage",)) is True


def test_unknown_change_domain_fails_closed() -> None:
    with pytest.raises(SecurityContractError,match="unknown changed threat domains"):
        canonical_vol026_threat_model().review_required(("magic",))


def test_duplicate_threat_identity_is_rejected() -> None:
    model=canonical_vol026_threat_model()
    duplicate=model.threats[0]
    with pytest.raises(SecurityContractError,match="duplicate threat id"):
        ThreatModel(model.threats+(duplicate,),impact_triggers=model.impact_triggers)


def test_impact_trigger_rejects_unknown_domain() -> None:
    with pytest.raises(SecurityContractError,match="unknown threat impact domains"):
        ThreatImpactTrigger("TR-X",("unknown",),"bad")
