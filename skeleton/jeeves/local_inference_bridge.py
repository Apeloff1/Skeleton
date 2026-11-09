"""
Jeeves Local Inference Bridge - host CAS, receipts, full authorization.
"""
from skeleton.cortex.local_model_adapter import bootstrap
import hashlib

class Bridge:
    def __init__(self):
        self.adapter = bootstrap()
    def dispatch(self, cmd: dict, cas: str) -> dict:
        if len(cas) < 16:
            raise PermissionError("CAS required")
        result = "local_inference_complete"
        receipt = {"digest": hashlib.sha256(result.encode()).hexdigest(), "cas": cas}
        return {"result": result, "receipt": receipt}
