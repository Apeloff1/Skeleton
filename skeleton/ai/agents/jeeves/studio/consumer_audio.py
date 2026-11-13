"""Consumer audio.
Optical-weighted audio cues for packs.
"""
from typing import Any, Dict

class ConsumerAudio:
    def cue(self, kind: str, optical: float) -> Dict[str, Any]:
        if not isinstance(kind, str) or not kind.strip():
            return {"ok": False, "reason": "empty_kind", "schema": "skeleton.audio.v1"}
        vol = round(0.5 + optical * 0.5, 2)
        return {"ok": True, "kind": kind, "volume": vol, "optical": optical, "reason": "ok", "schema": "skeleton.audio.v1"}
