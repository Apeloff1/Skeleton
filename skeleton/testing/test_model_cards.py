from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.component_provider_assurance import (
    ComponentProviderAssuranceError,
    build_model_card,
)

A="a"*64
B="b"*64
C="c"*64

def test_model_card_binds_mbom_and_evaluation_evidence()->None:
    card,evidence=build_model_card(
        component_id="model-1",version="v1",artifact_digest=A,
        intended_use="bounded assistant",limitations=("no medical authority",),
        mbom_digest=B,evaluation_digests=(C,),
    )
    assert card.kind=="model"
    assert card.evidence_refs==(f"mbom:{B}",f"eval:{C}")
    assert evidence.source_digests==(B,C)
    assert evidence.production_authority is False
    assert len(evidence.digest)==64

def test_model_card_requires_evaluation_evidence()->None:
    with pytest.raises(ComponentProviderAssuranceError,match="evaluation"):
        build_model_card(
            component_id="m",version="v1",artifact_digest=A,
            intended_use="test",limitations=("bounded",),
            mbom_digest=B,evaluation_digests=(),
        )
