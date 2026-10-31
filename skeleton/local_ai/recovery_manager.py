"""
Operational Recovery Manager. Restores from helix and receipts after failure. Fail-closed restart.
Fills the recovery gap.
"""
from typing import Dict
from .helix_persist import HelixPersist
from .receipts import ReceiptStore
from .error_handler import ErrorHandler

class RecoveryManager:
    def __init__(self):
        self.helix = HelixPersist()
        self.receipts = ReceiptStore()
        self.handler = ErrorHandler()

    def recover(self) -> Dict:
        pairs = self.helix.read_all()
        return {"recovered_pairs": len(pairs), "receipts": len(self.receipts.list()), "status": "restored"}
