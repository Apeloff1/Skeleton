"""Compatibility shim — re-exports `skeleton.shells.ai.schema`.

This shim exists so callers of `skeleton.ai.shell.schema` keep working while `skeleton.shells.ai.schema` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.schema import (
    action_schema,
    model_response_schema,
    schema_digest,
)

__all__ = ['action_schema', 'model_response_schema', 'schema_digest']
