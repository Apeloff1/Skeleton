"""Compatibility facade for the transitional shift-supervisor model gateway.

The credential-bearing implementation remains at
`core.shift_supervisor.model_gateway` during the staged AI-tree migration.
Keeping this destination as a pure re-export prevents a second credential or
network owner inside `skeleton.ai`.
"""

from core.shift_supervisor.model_gateway import ModelGateway, ModelRequestError

__all__ = ["ModelGateway", "ModelRequestError"]
