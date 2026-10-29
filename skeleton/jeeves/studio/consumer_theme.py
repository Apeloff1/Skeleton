"""Consumer theme.
Era-consistent palettes for end-user packs.
"""
from typing import Any, Dict

class ConsumerTheme:
    def apply(self, era: str, optical: float) -> Dict[str, Any]:
        if not isinstance(era, str) or not era.strip():
            return {"ok": False, "reason": "empty_era", "schema": "skeleton.theme.v1"}
        palette = "#3a2a1a" if era == "ash" else "#2a2a3a"
        return {"ok": True, "era": era, "palette": palette, "optical": optical, "reason": "ok", "schema": "skeleton.theme.v1"}
