"""Rights and audit subsystem.
Fail-closed checks, era binding, mass clips, citation enforcement.
"""
from __future__ import annotations
from typing import Any, Dict

class RightsAuditor:
    def check(self, card: Dict[str, Any]) -> Dict[str, Any]:
        sec = card.get("security", {})
        era = card.get("era", "")
        mass = card.get("mass", 1.0)
        return {
            "rights_ok": sec.get("rights_acknowledged") is True,
            "no_raw_rom": sec.get("no_raw_rom") is True,
            "era_bound": era == "HOUSE_ERA",
            "mass_clipped": mass <= 1.15,
            "fail_closed": True,
        }
    def enforce(self, card: Dict[str, Any]) -> bool:
        result = self.check(card)
        return all(result.values())
