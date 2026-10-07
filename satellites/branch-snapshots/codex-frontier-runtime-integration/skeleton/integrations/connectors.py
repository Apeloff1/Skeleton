"""
Skeleton Integrations — External service connectors

Provides:
- ConnectorRegistry: Register and manage external service connectors
- WebhookHandler: Receive and validate incoming webhooks
- APICredentials: Secure credential storage for external APIs
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class APICredentials:
    """Secure credential storage for external APIs."""
    service: str
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def mask_key(self) -> str:
        """Return masked API key for display."""
        if len(self.api_key) <= 8:
            return "***"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


class ConnectorRegistry:
    """Register and manage external service connectors."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._connectors: Dict[str, Dict[str, Any]] = {}
        self._credentials: Dict[str, APICredentials] = {}
        self._bus = bus
        self._stats = {"registered": 0, "calls": 0, "errors": 0}

    def register(self, name: str, base_url: str, handler: Optional[Callable] = None, credentials: Optional[APICredentials] = None) -> None:
        """Register a new connector."""
        self._connectors[name] = {
            "base_url": base_url,
            "handler": handler,
            "registered_at": time.time(),
            "calls": 0,
            "errors": 0,
        }
        
        if credentials:
            self._credentials[name] = credentials
        
        self._stats["registered"] += 1
        
        if self._bus:
            self._bus.emit("integrations.connector.registered", {
                "name": name,
                "base_url": base_url,
            })

    def get_connector(self, name: str) -> Optional[Dict[str, Any]]:
        return self._connectors.get(name)

    def get_credentials(self, name: str) -> Optional[APICredentials]:
        return self._credentials.get(name)

    def record_call(self, name: str, success: bool) -> None:
        """Record a connector call outcome."""
        if name in self._connectors:
            self._connectors[name]["calls"] += 1
            if not success:
                self._connectors[name]["errors"] += 1
                self._stats["errors"] += 1
            else:
                self._stats["calls"] += 1

    def health_check(self, name: str) -> Dict[str, Any]:
        """Check connector health."""
        connector = self._connectors.get(name)
        if not connector:
            return {"status": "not_found"}
        
        calls = connector.get("calls", 0)
        errors = connector.get("errors", 0)
        error_rate = errors / calls if calls > 0 else 0
        
        return {
            "status": "healthy" if error_rate < 0.1 else "degraded",
            "calls": calls,
            "errors": errors,
            "error_rate": error_rate,
            "last_call": connector.get("last_call"),
        }

    def list_connectors(self) -> List[str]:
        return list(self._connectors.keys())

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "active": len(self._connectors),
            "with_credentials": len(self._credentials),
        }


class WebhookHandler:
    """Receive and validate incoming webhooks from external services."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._secrets: Dict[str, str] = {}
        self._stats = {"received": 0, "verified": 0, "rejected": 0}

    def register_handler(self, source: str, secret: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a webhook handler for a source."""
        self._handlers[source] = handler
        self._secrets[source] = secret

    def verify(self, source: str, payload: bytes, signature: str) -> bool:
        """Verify webhook signature using HMAC-SHA256."""
        secret = self._secrets.get(source)
        if not secret:
            return False
        
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        # Support both hex and base64 signatures
        if signature.startswith("sha256="):
            signature = signature[7:]
        
        return hmac.compare_digest(signature, expected)

    def handle(self, source: str, payload: bytes, signature: str) -> Dict[str, Any]:
        """Handle an incoming webhook."""
        self._stats["received"] += 1
        
        if not self.verify(source, payload, signature):
            self._stats["rejected"] += 1
            return {"status": "rejected", "reason": "invalid_signature"}
        
        self._stats["verified"] += 1
        
        try:
            data = json.loads(payload)
            handler = self._handlers.get(source)
            if handler:
                handler(data)
            
            if self._bus:
                self._bus.emit("integrations.webhook.received", {
                    "source": source,
                    "event_type": data.get("event_type", "unknown"),
                })
            
            return {"status": "processed", "source": source}
        except json.JSONDecodeError:
            self._stats["rejected"] += 1
            return {"status": "rejected", "reason": "invalid_json"}
        except Exception as e:
            self._stats["rejected"] += 1
            return {"status": "rejected", "reason": str(e)}

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
