from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import build_agent_card

A="a"*64
B="b"*64
C="c"*64

def test_agent_card_binds_registry_and_performance_evidence()->None:
    card,evidence=build_agent_card(
        component_id="agent-1",version="v2",artifact_digest=A,
        intended_use="bounded research worker",limitations=("no production mutation",),
        agent_registry_digest=B,performance_evidence_digest=C,
    )
    assert card.kind=="agent"
    assert evidence.performance_evidence_digest==C
    assert f"performance:{C}" in card.evidence_refs
    assert evidence.production_authority is False
