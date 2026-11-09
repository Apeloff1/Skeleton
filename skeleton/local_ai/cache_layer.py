"""
Operational Cache Layer. Digest-keyed results for repeated prompts. Fail-closed on CAS mismatch.
Fills the latency gap.
"""
from typing import Dict, Optional
import hashlib

class CacheLayer:
    def __init__(self):
        self.store: Dict[str, Dict] = {}

    def key(self, prompt: str, cas: str) -> str:
        return hashlib.sha256(f"{prompt}|{cas}".encode()).hexdigest()

    def get(self, prompt: str, cas: str) -> Optional[Dict]:
        return self.store.get(self.key(prompt, cas))

    def put(self, prompt: str, cas: str, value: Dict) -> None:
        self.store[self.key(prompt, cas)] = value
