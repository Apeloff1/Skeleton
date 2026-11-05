"""One bounded strict JSON payload for all twenty domain observations."""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    LaptopGateHold, canonical,
)
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains
from skeleton.jeeves.native_fabric.laptop_ops.strict_json import decode
from .limits import DEFAULT_BUNDLE_LIMITS

BUNDLE_INPUT_SCHEMA = "jeeves.laptop_ops.bundle_evidence.v1"


def parse_bytes(raw: bytes) -> dict[str, object]:
    """Reject duplicate keys, invalid scalars, partial domains and extra data."""
    DEFAULT_BUNDLE_LIMITS.require_evidence_bytes(raw)
    value = decode(raw, maximum=DEFAULT_BUNDLE_LIMITS.max_evidence_bytes)
    if type(value) is not dict or set(value) != {"schema", "domains"}:
        raise LaptopGateHold("invalid source bundle envelope")
    if value["schema"] != BUNDLE_INPUT_SCHEMA:
        raise LaptopGateHold("unsupported source bundle envelope")
    domains = value["domains"]
    if type(domains) is not dict or set(domains) != set(list_domains()):
        raise LaptopGateHold("missing or unexpected first-laptop domains")
    for data in domains.values():
        if type(data) is not dict:
            raise LaptopGateHold("domain evidence must be an object")
    canonical(value, maximum=DEFAULT_BUNDLE_LIMITS.max_evidence_bytes)
    return domains


__all__ = ["parse_bytes", "BUNDLE_INPUT_SCHEMA"]
