"""skeleton/native/emulation_mapping.py
Fail-closed native emulation target mapping starter.
Tracks unmapped inventory, qualification receipts, no false boots.
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

_UNMAPPED_COUNT: Final[int] = 70

class EmulationError(SkeletonError):
    code = "NATIVE_EMU"
    severity = "medium"

@dataclass
class TargetCard:
    target_id: str
    mapped: bool = False
    core_approved: bool = False
    firmware_pinned: bool = False
    sdk_present: bool = False
    digest: str = ""

class EmulationFleet:
    def __init__(self) -> None:
        self.targets: dict[str, TargetCard] = {}
        self.unmapped: int = _UNMAPPED_COUNT

    def register(self, target_id: str) -> TargetCard:
        if target_id in self.targets:
            raise EmulationError("target already registered")
        card = TargetCard(target_id=target_id)
        payload = f"{target_id}:unmapped"
        card.digest = hashlib.sha256(payload.encode()).hexdigest()
        self.targets[target_id] = card
        emit_receipt(kind="emu_register", target=target_id, digest=card.digest, stored_prose=0)
        return card

    def qualify(self, target_id: str, core: bool, firmware: bool, sdk: bool) -> TargetCard:
        card = self.targets.get(target_id)
        if not card:
            raise EmulationError("unknown target")
        card.core_approved = core
        card.firmware_pinned = firmware
        card.sdk_present = sdk
        card.mapped = core and firmware and sdk
        if card.mapped:
            self.unmapped = max(0, self.unmapped - 1)
        payload = f"{target_id}:{card.mapped}:{core}:{firmware}:{sdk}"
        card.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(
            kind="emu_qualify",
            target=target_id,
            digest=card.digest,
            mapped=card.mapped,
            stored_prose=0,
        )
        return card

    def inventory(self) -> dict:
        return {
            "registered": len(self.targets),
            "unmapped_remaining": self.unmapped,
            "mapped": sum(1 for c in self.targets.values() if c.mapped),
        }
