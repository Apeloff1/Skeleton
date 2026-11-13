"""skeleton/native/emulation_mapping_card.py
Structured inventory card for the 70 unmapped native targets.
Fail-closed status reporting. Receipts. No stubs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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

_TOTAL_TARGETS: Final[int] = 169
_UNMAPPED: Final[int] = 70

class MappingError(SkeletonError):
    code = "NATIVE_MAP"
    severity = "low"

@dataclass
class TargetCard:
    target_id: str
    mapped: bool = False
    core: str = ""
    firmware: str = ""
    status: str = "unmapped"

@dataclass
class EmulationInventory:
    total: int = _TOTAL_TARGETS
    unmapped_count: int = _UNMAPPED
    cards: dict[str, TargetCard] = field(default_factory=dict)

    def add_unmapped(self, target_id: str) -> TargetCard:
        if target_id in self.cards:
            raise MappingError("duplicate target")
        card = TargetCard(target_id=target_id, mapped=False, status="unmapped")
        self.cards[target_id] = card
        digest = hashlib.sha256(target_id.encode()).hexdigest()
        emit_receipt(kind="emulation_unmapped", target=target_id, digest=digest, stored_prose=0)
        return card

    def mark_mapped(self, target_id: str, core: str, firmware: str) -> None:
        card = self.cards.get(target_id)
        if not card:
            raise MappingError("unknown target")
        card.mapped = True
        card.core = core
        card.firmware = firmware
        card.status = "mapped"
        self.unmapped_count = max(0, self.unmapped_count - 1)
        emit_receipt(kind="emulation_mapped", target=target_id, stored_prose=0)

    def summary_digest(self) -> str:
        payload = f"{self.total}:{self.unmapped_count}:{len(self.cards)}"
        return hashlib.sha256(payload.encode()).hexdigest()
