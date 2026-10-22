"""skeleton/repo_machine/shim_audit.py
Fail-closed transitional shim cleanup audit starter.
Inventories known shims, emits migration receipt. Never removes without explicit bind.
"""
from __future__ import annotations

import hashlib
from typing import Final

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_KNOWN_SHIMS: Final[tuple[str, ...]] = (
    "skeleton.deployment.*",
    "skeleton.contexts.*",
    "skeleton.galaxy.*",
    "skeleton.era.*",
    "skeleton.social.*",
)

class ShimAuditError(SkeletonError):
    code = "REPO_SHIM"
    severity = "low"

def audit_inventory() -> dict:
    inventory = {
        "known_shims": list(_KNOWN_SHIMS),
        "count": len(_KNOWN_SHIMS),
        "status": "audited",
        "stored_prose": 0,
    }
    digest = hashlib.sha256(str(sorted(inventory.items())).encode()).hexdigest()
    emit_receipt(kind="shim_audit", digest=digest, count=len(_KNOWN_SHIMS), stored_prose=0)
    return inventory

def mark_migrated(shim: str) -> str:
    if shim not in _KNOWN_SHIMS:
        raise ShimAuditError("unknown shim")
    digest = hashlib.sha256(shim.encode()).hexdigest()
    emit_receipt(kind="shim_migrated", target=shim, digest=digest, stored_prose=0)
    return digest
