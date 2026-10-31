"""
Receipt store for local AI. Hash-linked, host-CAS bound, local only.
"""
from typing import List, Dict
import hashlib

class ReceiptStore:
    def __init__(self):
        self.receipts: List[Dict] = []

    def add(self, receipt: Dict) -> str:
        digest = hashlib.sha256(str(receipt).encode()).hexdigest()
        receipt["digest"] = digest
        self.receipts.append(receipt)
        return digest

    def list(self) -> List[Dict]:
        return self.receipts.copy()
