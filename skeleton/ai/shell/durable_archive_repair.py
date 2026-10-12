"""Compatibility shim — re-exports `skeleton.shells.ai.durable_archive_repair`.

This shim exists so callers of `skeleton.ai.shell.durable_archive_repair` keep working while `skeleton.shells.ai.durable_archive_repair` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_archive_repair import (
    ArchiveIndexRepairAction,
    ArchiveIndexRepairState,
    ArchiveIndexRepairPolicy,
    ArchiveIndexRepairPlan,
    ArchiveIndexRepairResult,
    ArchiveIndexRepairBatchReport,
    ArchiveIndexRepairError,
    DurableArchiveIndexRepairCoordinator,
)

__all__ = ['ArchiveIndexRepairAction', 'ArchiveIndexRepairState', 'ArchiveIndexRepairPolicy', 'ArchiveIndexRepairPlan', 'ArchiveIndexRepairResult', 'ArchiveIndexRepairBatchReport', 'ArchiveIndexRepairError', 'DurableArchiveIndexRepairCoordinator']
