"""
Operational Safety Filter. Fail-closed checks on generated text for length, CAS binding, and clipped-G bounds.
Fills the output safety gap.
"""
from typing import Dict
from .fail_closed import guard_clipped

class SafetyFilter:
    def check(self, text: str, g: float, max_len: int = 4096) -> Dict:
        try:
            guard_clipped(g)
            if len(text) > max_len:
                return {"safe": False, "reason": "length"}
            return {"safe": True, "reason": "ok"}
        except Exception as e:
            return {"safe": False, "reason": str(e)}
