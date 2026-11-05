"""Read-only proof projection from an already-authenticated committed receipt."""
from __future__ import annotations
from ..contracts import SpineError, hexdigest
from .proofs import validate_decision


def from_receipt(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        raise SpineError('committed turn receipt required')
    meta = receipt.get('context_capacity')
    if meta is None:
        return {'status':'legacy-receipt-no-capacity-metadata'}
    validate_decision(meta)
    if receipt.get('context_sha256') != meta['projection_sha256']:
        raise SpineError('receipt and context capacity disagree')
    if receipt.get('omitted_turns') != meta['omitted_turns']:
        raise SpineError('receipt and context omission count disagree')
    refs = receipt.get('evidence_refs')
    if not isinstance(refs,list) or len(refs) != meta['retained_sources']:
        raise SpineError('source receipt count does not match projection')
    return meta | {'status':'integrity-bound-context-decision-not-release-certification'}
