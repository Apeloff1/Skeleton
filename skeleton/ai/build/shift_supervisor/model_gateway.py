"""Compatibility facade for the canonical shift-supervisor model gateway.

The credential-bearing implementation remains singular at
`skeleton.automation.shift_supervisor.model_gateway`. Keeping this AI-tree
destination as a pure re-export prevents a second credential or network owner
inside `skeleton.ai`.
"""

from skeleton.automation.shift_supervisor.model_gateway import ModelGateway, ModelRequestError

__all__ = ["ModelGateway", "ModelRequestError"]
