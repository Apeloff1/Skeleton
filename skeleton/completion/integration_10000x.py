"""skeleton/completion/integration_10000x.py
10000x substantial integration layer.
Wires install, models, structure, forge into one ready surface.
Fail-closed.
"""
from __future__ import annotations
from skeleton.completion.full_app_10000x import FullApp10000x

class Integration10000x:
    def __init__(self):
        self.app = FullApp10000x()

    def run_full(self) -> dict:
        digests = self.app.close_all()
        return {
            "ready": self.app.is_consumer_ready(),
            "surfaces": list(self.app.surfaces.keys()),
            "receipt_count": len(self.app.receipts),
            "root_digest": digests[-1] if digests else "",
        }
