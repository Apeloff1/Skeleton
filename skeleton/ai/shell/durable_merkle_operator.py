"""Compatibility shim — re-exports `skeleton.shells.ai.durable_merkle_operator`.

This shim exists so callers of `skeleton.ai.shell.durable_merkle_operator` keep working while `skeleton.shells.ai.durable_merkle_operator` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_merkle_operator import (
    DurableMerkleOperatorStatus,
    DurableMerkleOperatorResult,
    DurableMerkleOperatorError,
    DurableSessionMerkleOperator,
)

__all__ = ['DurableMerkleOperatorStatus', 'DurableMerkleOperatorResult', 'DurableMerkleOperatorError', 'DurableSessionMerkleOperator']
