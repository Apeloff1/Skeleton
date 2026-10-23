"""
Unified facade for local AI. Combines adapter, bridge, receipts, observability, and fail-closed guards.
"""
from .local_ai_complete import get_complete
from .receipts import ReceiptStore
from .observability import Observability
from .fail_closed import guard_cas, guard_clipped

class LocalAIFacade:
    def __init__(self):
        self.complete = get_complete()
        self.receipts = ReceiptStore()
        self.obs = Observability()

    def dispatch(self, cmd: dict, cas: str) -> dict:
        guard_cas(cas)
        result = self.complete.bridge.dispatch(cmd, cas)
        digest = self.receipts.add(result.get("receipt", {}))
        self.obs.record("last_digest", float(int(digest[:8], 16) % 1000))
        return {"result": result, "receipt_digest": digest, "obs": self.obs.stamp()}
