"""skeleton/knowledge/graphs/sheaf_facade.py
Thin production facade for sheaf research layer promotion.
Exports capability card, lineage citation, fail-closed receipt. No tree copy.
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

_SHEAF_LINEAGE: Final[str] = "research/sheaf/experimental"

class SheafFacadeError(SkeletonError):
    code = "KNOW_SHEAF"
    severity = "medium"

def capabilities() -> dict:
    """Export owner contract, failure modes, obs, security for sheaf facade."""
    card = {
        "kind": "sheaf_facade",
        "hit": True,
        "law": "thin-adapter",
        "citation": _SHEAF_LINEAGE,
        "stored_prose": 0,
        "failure_modes": ["unbound_section", "cech_mismatch"],
        "security": "read-only research view",
    }
    digest = hashlib.sha256(str(sorted(card.items())).encode()).hexdigest()
    emit_receipt(kind="sheaf_capability", digest=digest, stored_prose=0)
    return card

def promote_section(section_id: str, bound: bool = True) -> str:
    if not bound:
        raise SheafFacadeError("section must be bound before promotion")
    digest = hashlib.sha256(section_id.encode()).hexdigest()
    emit_receipt(kind="sheaf_promote", target=section_id, digest=digest, stored_prose=0)
    return digest
