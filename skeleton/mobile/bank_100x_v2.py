"""skeleton/mobile/bank_100x_v2.py
Further 100x extreme Mobile bank.
Defaults off for heavy planes. Bank card stays green.
Fail-closed.
"""
from __future__ import annotations

class BankError(Exception):
    pass

class MobileBank100xV2:
    HEAVY = {"speculative_rag", "sse", "bench_gpu", "hf_import"}

    def is_green(self, plane: str, mobile: bool = False) -> bool:
        if mobile and plane in self.HEAVY:
            return False
        return True
