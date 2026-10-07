"""Compatibility facade for the canonical shift-supervisor model gateway.

The AI build tree keeps its import path for compatibility while provider
credentials, raw network transport, retry policy, and architecture receipts
remain owned by :mod:`skeleton.automation.shift_supervisor.model_gateway`.
"""

from skeleton.automation.shift_supervisor.model_gateway import (
    ModelGateway,
    ModelRequestError,
)

__all__ = [
    "ModelGateway",
    "ModelRequestError",
]
