"""Layered analysis chain regression tests."""
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import (
    AnalysisLayer, DEFAULT_CHAIN, LayerReceipt, validate_chain,
)


def receipts():
    output = {}
    result = []
    for index, spec in enumerate(DEFAULT_CHAIN):
        digest = f"{index + 1:064x}"
        result.append(LayerReceipt(
            spec.layer, tuple(output[dep] for dep in spec.dependencies),
            digest, max(2, spec.min_independent_sources),
            True, spec.requires_human,
        ))
        output[spec.layer] = digest
    return tuple(result)


def test_complete_chain():
    verdict = validate_chain(receipts(), authorized=True)
    assert verdict.complete
    assert len(verdict.accepted_layers) == 12


def test_missing_stage_cannot_promote_memory():
    rows = tuple(x for x in receipts() if x.layer is not AnalysisLayer.CAUSAL_FALSIFICATION)
    verdict = validate_chain(rows, authorized=True)
    assert not verdict.complete
    assert AnalysisLayer.MEMORY_PROMOTION in verdict.rejected_layers


def test_evidence_fingerprint_tampering_rejected():
    from dataclasses import replace
    rows = list(receipts())
    rows[4] = replace(rows[4], input_fingerprints=("f" * 64,))
    verdict = validate_chain(tuple(rows), authorized=True)
    assert AnalysisLayer.MECHANIC_HYPOTHESES in verdict.rejected_layers


def test_human_approval_cannot_be_implicit():
    from dataclasses import replace
    rows = list(receipts())
    rows[10] = replace(rows[10], human_approved=False)
    verdict = validate_chain(tuple(rows), authorized=True)
    assert AnalysisLayer.HUMAN_APPROVAL in verdict.rejected_layers
    assert not verdict.complete


def test_independent_source_threshold():
    from dataclasses import replace
    rows = list(receipts())
    rows[6] = replace(rows[6], independent_sources=1)
    verdict = validate_chain(tuple(rows), authorized=True)
    assert AnalysisLayer.CROSS_SOURCE_CORROBORATION in verdict.rejected_layers


def test_duplicate_receipts_rejected():
    rows = receipts()
    with pytest.raises(ValueError, match="duplicate"):
        validate_chain(rows + (rows[0],), authorized=True)


def test_authorization_required():
    with pytest.raises(PermissionError):
        validate_chain(receipts(), authorized=False)


def test_receipt_order_does_not_change_verdict():
    a = validate_chain(receipts(), authorized=True)
    b = validate_chain(tuple(reversed(receipts())), authorized=True)
    assert a == b
