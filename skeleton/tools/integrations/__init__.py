"""
Skeleton Integrations Package

Exports:
- ConnectorRegistry: External service connectors
- WebhookHandler: Incoming webhook validation
- APICredentials: Secure credential storage
"""

from skeleton.tools.integrations.connectors import (
    APICredentials,
    ConnectorRegistry,
    WebhookHandler,
)

__all__ = [
    "ConnectorRegistry",
    "WebhookHandler",
    "APICredentials",
]
