"""Typed HTTP client for Skeleton Backend APIs and the Middleware gateway.

Consumers (CLI, cockpit, scripts) should go through this package instead of
raw httpx/requests. Extend-only: add methods as new routes land.
"""

from skeleton.client.agents import AgentsClient
from skeleton.client.auth import AuthClient
from skeleton.client.builds import BuildsClient
from skeleton.client.cancel import CancelToken
from skeleton.client.errors import (
    SkeletonCancelledError,
    SkeletonClientError,
    SkeletonHTTPError,
    SkeletonSealConfigError,
    SkeletonTimeoutError,
    SkeletonTransportError,
)
from skeleton.client.gateway import GatewayClient
from skeleton.client.memory import MemoryClient
from skeleton.client.retry import RetryPolicy
from skeleton.client.seal import RequestSealer
from skeleton.client.services import ServicesClient
from skeleton.client.streaming import StreamEvent

__all__ = [
    "AgentsClient",
    "AuthClient",
    "BuildsClient",
    "CancelToken",
    "GatewayClient",
    "MemoryClient",
    "RequestSealer",
    "RetryPolicy",
    "ServicesClient",
    "SkeletonCancelledError",
    "SkeletonClientError",
    "SkeletonHTTPError",
    "SkeletonSealConfigError",
    "SkeletonTimeoutError",
    "SkeletonTransportError",
    "StreamEvent",
]
