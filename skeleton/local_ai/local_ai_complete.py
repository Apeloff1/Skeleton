"""Legacy local-AI seam inventory, not an inference readiness probe.

Real model dispatch belongs to skeleton.provider_runtime. Constructing a
local adapter or a bridge does not prove that a GGUF model, tokenizer,
reviewer or shared guard has been activated.
"""
from skeleton.local_ai.local_ai_index import SEAMS
from skeleton.cortex.local_model_adapter import bootstrap
from skeleton.jeeves.local_inference_bridge import Bridge


class LocalAIComplete:
    def __init__(self):
        self.adapter = bootstrap()
        self.bridge = Bridge()
        self.seams = SEAMS

    def status(self) -> dict:
        return {
            "seams": len(self.seams),
            "adapter": "legacy_unverified",
            "bridge": "disabled_unverified",
            "status": "unavailable",
            "readiness_code": "LOCAL_INFERENCE_NOT_BOUND",
            "ready": False,
        }


def get_complete() -> LocalAIComplete:
    return LocalAIComplete()
