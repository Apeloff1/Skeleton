"""Eight independently checked model_manifest safeguards (never activation authority)."""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    archive_source_digest,
    installed_model_digest,
    tokenizer_source_digest,
    source_approval,
    rights_revocation,
    manifest_revision,
    license_owner,
    inspection_window,
)

DOMAIN = "model_manifest"
STAGES = ("archive_source_digest", "installed_model_digest", "tokenizer_source_digest", "source_approval", "rights_revocation", "manifest_revision", "license_owner", "inspection_window",)
STAGE_TYPES = (("archive_source_digest", "sha_equal"), ("installed_model_digest", "sha_equal"), ("tokenizer_source_digest", "sha_equal"), ("source_approval", "true"), ("rights_revocation", "false"), ("manifest_revision", "monotonic"), ("license_owner", "same_owner"), ("inspection_window", "fresh"),)
HANDLERS = (archive_source_digest, installed_model_digest, tokenizer_source_digest, source_approval, rights_revocation, manifest_revision, license_owner, inspection_window,)


def evaluate(evidence: object):
    """Require every stage in the declared order; never infer missing proof."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or unknown model_manifest safeguard")
    results = tuple(handler.check(evidence[stage])
                    for stage, handler in zip(STAGES, HANDLERS))
    if len(results) != 8:
        raise LaptopGateHold("incomplete model_manifest evaluation")
    return results


def contracts() -> tuple[dict[str, object], ...]:
    """Stable public schema for the eight independent stage predicates."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
