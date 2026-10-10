"""Compatibility shim — re-exports `skeleton.shells.ai.policy_migration`.

This shim exists so callers of `skeleton.ai.shell.policy_migration` keep working while `skeleton.shells.ai.policy_migration` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.policy_migration import (
    AIPolicyChangeRisk,
    AIPolicyChange,
    AIPolicyMigration,
    AIPolicyMigrationPlanner,
)

__all__ = ['AIPolicyChangeRisk', 'AIPolicyChange', 'AIPolicyMigration', 'AIPolicyMigrationPlanner']
