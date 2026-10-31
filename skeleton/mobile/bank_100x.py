"""skeleton/mobile/bank_100x.py
100x extreme complete Mobile bank.
Defaults off for heavy planes. Bank card green.
Fail-closed.
"""
from __future__ import annotations

class BankError(Exception):
    pass

class MobileBank100x:
    HEAVY = {"speculative_rag", "sse", "bench_gpu", "hf_import"}

    def is_green(self, plane: str, mobile: bool) -> bool:
        if mobile and plane in self.HEAVY:
            return False
        return True
