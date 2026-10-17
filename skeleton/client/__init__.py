"""Typed HTTP client for Skeleton Backend APIs and the Middleware gateway.

Consumers (CLI, cockpit, scripts) should go through this package instead of
raw httpx/requests. Extend-only: add methods as new routes land.
"""

from skeleton.client.errors import (
    SkeletonClientError,
    SkeletonHTTPError,
    SkeletonTimeoutError,
    SkeletonTransportError,
)
from skeleton.client.gateway import GatewayClient
from skeleton.client.memory import MemoryClient
from skeleton.client.services import ServicesClient

__all__ = [
    "GatewayClient",
    "MemoryClient",
    "ServicesClient",
    "SkeletonClientError",
    "SkeletonHTTPError",
    "SkeletonTimeoutError",
    "SkeletonTransportError",
]
