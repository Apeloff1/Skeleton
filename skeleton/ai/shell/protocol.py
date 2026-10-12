"""Compatibility shim — re-exports `skeleton.shells.ai.protocol`.

This shim exists so callers of `skeleton.ai.shell.protocol` keep working while `skeleton.shells.ai.protocol` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.protocol import (
    AI_MODEL_PROTOCOL_VERSION,
    ModelProtocolError,
    AIModelRequest,
    AIModelResponse,
    parse_model_response,
)

__all__ = ['AI_MODEL_PROTOCOL_VERSION', 'ModelProtocolError', 'AIModelRequest', 'AIModelResponse', 'parse_model_response']
