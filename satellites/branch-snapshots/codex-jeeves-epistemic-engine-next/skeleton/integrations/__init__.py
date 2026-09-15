"""
Skeleton Integrations Package

Exports:
- ConnectorRegistry: External service connectors
- WebhookHandler: Incoming webhook validation
- APICredentials: Secure credential storage
"""

from skeleton.integrations.connectors import (
    APICredentials,
    ConnectorRegistry,
    WebhookHandler,
)

__all__ = [
    "ConnectorRegistry",
    "WebhookHandler",
    "APICredentials",
]
