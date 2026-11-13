"""Backend core v1: shared API kernel (errors, pagination, idempotency,
optimistic concurrency) plus the durable webhooks domain.

Hexagonal layout:
  * ``errors``, ``pagination``, ``concurrency``, ``ids``, ``clock`` - pure kernel.
  * ``ports`` - repository / transport / URL-policy protocols.
  * ``sqlite_store`` - adapters on ``skeleton.persistence.app_foundation.db.Database``.
  * ``memory_store`` - in-memory adapters (conformance + tests).
  * ``webhooks`` - application service; no I/O except through ports.

FastAPI wiring lives in ``routes.core_v1_webhooks``; the router is not
mounted here (Middleware owns the edge, see
docs/architecture/contracts/backend_core_v1.md).
"""
from __future__ import annotations

CONTRACT_ID = "skeleton.backend_core.v1"
CONTRACT_VERSION = "1.0.0"

__all__ = ["CONTRACT_ID", "CONTRACT_VERSION"]
