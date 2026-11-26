"""Cloud save stub. In-memory digest pointer; no remote transfer is performed."""
from typing import Any, Dict


class CloudSave:
    def __init__(self) -> None:
        self.slots: Dict[str, str] = {}

    def push(self, digest: str, slot: str) -> Dict[str, Any]:
        if not _digest_ok(digest) or not _slot_ok(slot):
            return {"ok": False, "slot": slot, "digest": None, "synced": False, "reason": "rejected"}
        self.slots[slot] = digest
        return {"ok": True, "slot": slot, "digest": digest, "synced": False, "reason": "local_only"}

    def pull(self, slot: str) -> Dict[str, Any]:
        if not isinstance(slot, str) or slot not in self.slots:
            return {"ok": False, "slot": slot, "digest": None, "synced": False, "reason": "unknown_slot"}
        return {"ok": True, "slot": slot, "digest": self.slots[slot], "synced": False, "reason": "local_only"}


def _digest_ok(digest: str) -> bool:
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in digest)


def _slot_ok(slot: str) -> bool:
    return isinstance(slot, str) and 0 < len(slot) <= 32
