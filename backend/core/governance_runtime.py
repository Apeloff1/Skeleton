"""Shared durable governance runtime for backend production surfaces.

This module owns one process-local handle over durable lifecycle metadata, WORM
audit state, canonical governed artifact bytes, and lifecycle adapters.  It is a
composition boundary only: policy/state authority remains in skeleton.vault and
physical artifact authority remains in skeleton.artifact_plane.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading

from skeleton.artifact_plane.governance import GovernedArtifactStore
from skeleton.vault.audit import AuditLog
from skeleton.vault.data_lifecycle import DataLifecycleRegistry
from skeleton.vault.governance_audit import GovernanceAuditTimeline
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.vault.lifecycle_adapters import (
    GovernedArtifactLifecycleAdapter,
    LifecycleAdapterRegistry,
)


def _state_root() -> Path:
    configured = os.environ.get("BACKEND_GOVERNANCE_STATE_DIR", "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        root = Path(__file__).resolve().parents[1] / "state" / "governance"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _artifact_root(state_root: Path) -> Path:
    configured = os.environ.get("BACKEND_GOVERNED_ARTIFACT_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        # Keep governed build artifacts under the existing backend artifact tree
        # so deployment volume policies and download compatibility remain intact.
        root = Path(__file__).resolve().parents[1] / "artifacts" / "builds"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


@dataclass(slots=True)
class BackendGovernanceRuntime:
    lifecycle: DataLifecycleRegistry
    audit_log: AuditLog
    timeline: GovernanceAuditTimeline
    registry: GovernanceRegistry
    artifacts: GovernedArtifactStore
    adapters: LifecycleAdapterRegistry

    def close(self) -> None:
        self.lifecycle.close()


_lock = threading.RLock()
_runtime: BackendGovernanceRuntime | None = None


def build_backend_governance_runtime() -> BackendGovernanceRuntime:
    root = _state_root()
    lifecycle = DataLifecycleRegistry(root / "lifecycle.sqlite3")
    audit_log = AuditLog.open(root / "governance-audit.jsonl")
    timeline = GovernanceAuditTimeline(
        audit_log,
        actor="backend-governance-runtime",
    )
    registry = GovernanceRegistry(
        lifecycle,
        timeline=timeline,
    )
    artifacts = GovernedArtifactStore(
        _artifact_root(root),
        registry,
    )
    adapters = LifecycleAdapterRegistry()
    artifact_adapter = GovernedArtifactLifecycleAdapter(artifacts)
    adapters.register_deletion("artifact", artifact_adapter)
    adapters.register_export("artifact", artifact_adapter)
    return BackendGovernanceRuntime(
        lifecycle=lifecycle,
        audit_log=audit_log,
        timeline=timeline,
        registry=registry,
        artifacts=artifacts,
        adapters=adapters,
    )


def get_backend_governance_runtime() -> BackendGovernanceRuntime:
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = build_backend_governance_runtime()
        return _runtime


def close_backend_governance_runtime() -> None:
    global _runtime
    with _lock:
        current = _runtime
        _runtime = None
    if current is not None:
        current.close()


__all__ = [
    "BackendGovernanceRuntime",
    "build_backend_governance_runtime",
    "close_backend_governance_runtime",
    "get_backend_governance_runtime",
]
