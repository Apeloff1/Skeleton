"""Payload-free public diagnostic projection, not a logging replacement."""
from __future__ import annotations
from .contracts import LaptopGateHold, canonical, fingerprint, name


def diagnostic(reason: str, *, stage: str | None = None) -> dict[str, object]:
    if type(reason) is not str or not reason or len(reason) > 128:
        raise LaptopGateHold("bounded reason code required")
    if stage is not None:
        name(stage)
    # Intentionally omit private paths, prompts, tokens and exception text.
    return {"schema": "jeeves.laptop_ops.diagnostic.v1",
            "status": "held", "reason_sha256": fingerprint(reason),
            "stage": stage, "release_certified": False}


def summary(*, accepted: bool, count: int, evidence: object) -> dict[str, object]:
    if type(accepted) is not bool or type(count) is not int:
        raise LaptopGateHold("strict diagnostic summary")
    if not 0 <= count <= 256:
        raise LaptopGateHold("unbounded safeguard count")
    canonical(evidence)
    return {"schema": "jeeves.laptop_ops.summary.v1",
            "accepted_source_only": accepted,
            "safeguards_checked": count,
            "evidence_sha256": fingerprint(evidence),
            "real_model_executed": False,
            "release_certified": False}
