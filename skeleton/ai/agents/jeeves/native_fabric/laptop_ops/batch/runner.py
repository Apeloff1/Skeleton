"""All twenty first-laptop source contracts evaluated as one pure bundle.

This is not an alternate GGUF provider, supervisor, workspace, or release
authority. A failed domain never gets skipped or counted as a pass.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    LaptopGateHold, canonical, fingerprint,
)
from skeleton.jeeves.native_fabric.laptop_ops.runner import (
    evaluate_domain, list_domains,
)
from .catalog import manifest
from .limits import DEFAULT_BUNDLE_LIMITS
from .records import SourceBundle
from .schema import parse_bytes


def evaluate_bundle(evidence: object) -> SourceBundle:
    """Check exact all-domains input, then each source safeguard in order."""
    ordered = list_domains()
    if type(evidence) is not dict or set(evidence) != set(ordered):
        raise LaptopGateHold("twenty named domain observations required")
    canonical(evidence, maximum=DEFAULT_BUNDLE_LIMITS.max_evidence_bytes)
    source = manifest()
    results = tuple(evaluate_domain(domain, evidence[domain])
                    for domain in ordered)
    if len(results) != 20 or any(len(r.stages) != 8 for r in results):
        raise LaptopGateHold("source bundle evaluation incomplete")
    return SourceBundle(
        results, source["manifest_sha256"],
        fingerprint({"schema": "jeeves.laptop_ops.bundle_evidence.v1",
                     "domains": evidence}),
    )


def evaluate_json(raw: bytes) -> SourceBundle:
    """Reject ambiguous JSON before any evaluation; no model is opened."""
    return evaluate_bundle(parse_bytes(raw))


__all__ = ["evaluate_bundle", "evaluate_json"]
