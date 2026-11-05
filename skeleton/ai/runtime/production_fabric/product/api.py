"""Compatibility API import; the local product dispatcher owns operations.

Existing callers can keep importing product.api.LocalAPI. Runtime-domain
orchestration imports the implementation from dispatcher to avoid upward API
dependencies. No HTTP server, permission grant or hosted model is created.
"""
from .dispatcher import LocalAPI

__all__ = ["LocalAPI"]
