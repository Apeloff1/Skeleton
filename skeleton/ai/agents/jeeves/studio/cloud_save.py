"""Cloud save stub. Digest-based remote pointer."""
from typing import Any, Dict
class CloudSave:
    def push(self, digest: str, slot: str) -> Dict[str, Any]:
        return {"slot": slot, "digest": digest, "synced": True}
    def pull(self, slot: str) -> Dict[str, Any]:
        return {"slot": slot, "digest": None}
