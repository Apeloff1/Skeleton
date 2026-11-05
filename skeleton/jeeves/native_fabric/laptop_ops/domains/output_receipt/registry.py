"""Reconcile committed native output against read-only replay evidence before delivery.

All eight source-only observations are required. Consistent synthetic input
is never proof of a real running model, source license or physical device.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    committed_digest,
    replayed_digest,
    prompt_digest,
    tokenizer_digest,
    sqlite_commit,
    token_count,
    journal_sequence,
    receipt_observation,
)

DOMAIN = "output_receipt"
STAGES = ("committed_digest", "replayed_digest", "prompt_digest", "tokenizer_digest", "sqlite_commit", "token_count", "journal_sequence", "receipt_observation",)
STAGE_TYPES = (("committed_digest", "sha_equal"), ("replayed_digest", "sha_equal"), ("prompt_digest", "sha_equal"), ("tokenizer_digest", "sha_equal"), ("sqlite_commit", "true"), ("token_count", "bounded"), ("journal_sequence", "monotonic"), ("receipt_observation", "fresh"),)
HANDLERS = (committed_digest, replayed_digest, prompt_digest, tokenizer_digest, sqlite_commit, token_count, journal_sequence, receipt_observation,)


def evaluate(evidence: object):
    """Fail closed on missing stages and mutually inconsistent source claims."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or extra output_receipt source safeguard")
    observed = tuple(handler.check(evidence[stage])
                     for stage, handler in zip(STAGES, HANDLERS))
    if len(observed) != 8 or len({item.stage for item in observed}) != 8:
        raise LaptopGateHold("incomplete output_receipt stage inventory")
    if all(item.accepted for item in observed) and not (evidence["committed_digest"]["observed_sha256"] == evidence["replayed_digest"]["observed_sha256"]):
        raise LaptopGateHold("inconsistent output_receipt cross-stage facts")
    return observed


def contracts() -> tuple[dict[str, object], ...]:
    """Publish stable stage input inventory, not native startup authorization."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
