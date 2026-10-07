"""Compatibility facade for the canonical repository model client.

Provider credentials, endpoint validation, network transport, cancellation,
and architecture receipts are owned by :mod:`skeleton.automation.free_model`.
"""

from skeleton.automation.free_model import (
    FreeModelClient,
    ModelError,
    redact_secrets,
)

__all__ = [
    "FreeModelClient",
    "ModelError",
    "redact_secrets",
]
