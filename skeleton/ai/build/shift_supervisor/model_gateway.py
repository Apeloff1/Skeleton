"""Non-owning compatibility facade for the shift-supervisor model gateway.

Credential, provider-network and retry ownership remains canonical in
skeleton.automation.shift_supervisor.model_gateway until explicit cutover.
"""

from skeleton.automation.shift_supervisor.model_gateway import ModelGateway, ModelRequestError

__all__ = ["ModelGateway", "ModelRequestError"]
