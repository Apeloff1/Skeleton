from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import build_dataset_card

A="a"*64
B="b"*64
C="c"*64

def test_dataset_card_binds_registry_and_lineage()->None:
    card,evidence=build_dataset_card(
        component_id="dataset-1",version="2026.10",artifact_digest=A,
        intended_use="offline evaluation",limitations=("licensed research only",),
        dataset_registry_digest=B,lineage_digest=C,
    )
    assert card.kind=="dataset"
    assert evidence.source_digests==(B,C)
    assert card.evidence_refs==(f"dataset-registry:{B}",f"lineage:{C}")
    assert evidence.production_authority is False
