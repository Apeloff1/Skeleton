from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import build_tool_card

A="a"*64
B="b"*64
C="c"*64

def test_tool_card_requires_and_binds_security_review()->None:
    card,evidence=build_tool_card(
        component_id="tool-1",version="v1",artifact_digest=A,
        intended_use="read-only lookup",limitations=("no arbitrary shell",),
        tool_definition_digest=B,security_review_digest=C,
    )
    assert card.kind=="tool"
    assert evidence.security_review_digest==C
    assert f"security-review:{C}" in card.evidence_refs
    assert evidence.production_authority is False
