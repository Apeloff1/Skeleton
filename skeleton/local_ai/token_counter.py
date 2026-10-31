"""
Operational Token Counter. Estimates and tracks token usage against clipped-G mass.
Fills the accounting gap.
"""
from typing import Dict

class TokenCounter:
    def __init__(self):
        self.total = 0

    def count(self, text: str) -> int:
        # Simple operational estimate
        n = max(1, len(text.split()) // 4)
        self.total += n
        return n

    def report(self) -> Dict:
        return {"total_tokens": self.total, "mass_proxy": self.total / 1000.0}
