"""skeleton/foundation/architecture/genos_cutover.py
Fail-closed specialized runtime cutover starter for genos.
Ownership card and lineage. No production authority until explicit bind.
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

_GENOS_LINEAGE: Final[str] = "unresolved/genos"

class CutoverError(SkeletonError):
    code = "FOUND_CUTOVER"
    severity = "medium"

def ownership_card(bound: bool = False) -> dict:
    card = {
        "kind": "genos_cutover",
        "hit": bound,
        "law": "explicit-owner",
        "citation": _GENOS_LINEAGE,
        "stored_prose": 0,
        "status": "bound" if bound else "unresolved",
    }
    digest = hashlib.sha256(str(sorted(card.items())).encode()).hexdigest()
    emit_receipt(kind="genos_ownership", digest=digest, bound=bound, stored_prose=0)
    return card

def bind_owner(owner: str) -> str:
    if not owner or not owner.startswith("skeleton."):
        raise CutoverError("owner must be canonical skeleton path")
    digest = hashlib.sha256(owner.encode()).hexdigest()
    emit_receipt(kind="genos_bind", target=owner, digest=digest, stored_prose=0)
    return digest
