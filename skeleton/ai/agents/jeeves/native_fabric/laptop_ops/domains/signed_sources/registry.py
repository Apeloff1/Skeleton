"""Keep signed offline source manifests, operator approval and revocation in a single scope.

Observe eight independent stages and cross-check one authority-critical
relationship. This is a typed source-only diagnostic, not GGUF activation.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    signed_manifest,
    loaded_manifest,
    license_approval,
    owner,
    source_count,
    rights_revision,
    observed_at,
    revoked,
)

DOMAIN = "signed_sources"
STAGES = ("signed_manifest", "loaded_manifest", "license_approval", "owner", "source_count", "rights_revision", "observed_at", "revoked",)
STAGE_TYPES = (("signed_manifest", "sha_equal"), ("loaded_manifest", "sha_equal"), ("license_approval", "true"), ("owner", "same_owner"), ("source_count", "bounded"), ("rights_revision", "monotonic"), ("observed_at", "fresh"), ("revoked", "false"),)
HANDLERS = (signed_manifest, loaded_manifest, license_approval, owner, source_count, rights_revision, observed_at, revoked,)


def evaluate(evidence: object):
    """Do not admit partial, malformed or inconsistent observations."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or extra signed_sources source evidence")
    verdicts = tuple(handler.check(evidence[name])
                     for name, handler in zip(STAGES, HANDLERS))
    if len(verdicts) != 8 or len({v.stage for v in verdicts}) != 8:
        raise LaptopGateHold("incomplete signed_sources stage roster")
    if all(v.accepted for v in verdicts) and not (evidence["signed_manifest"]["observed_sha256"] == evidence["loaded_manifest"]["observed_sha256"]):
        raise LaptopGateHold("incoherent signed_sources cross-stage source identity")
    return verdicts


def contracts() -> tuple[dict[str, object], ...]:
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
