"""Audit trail helpers over OmniFabric — exportable evidence packs.

Produces reviewer-friendly audit documents combining chain reports,
merkle checkpoints, ledger histograms, and projection status without
coupling to api.server lifespan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.omnifabric.doctrine import DOCTRINE, SIBLING_MODULE, SIBLING_PATH, SIBLING_REPO
from skeleton.kernel.omnifabric.service import OmniFabricService
from skeleton.kernel.omnifabric.verify import evidence_bundle


@dataclass
class AuditPack:
    generated_at: float = field(default_factory=time.time)
    sibling: dict[str, str] = field(default_factory=dict)
    doctrine_keys: list[str] = field(default_factory=list)
    fabric_stats: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)
    projections: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    windows: dict[str, Any] = field(default_factory=dict)
    checkpoints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "sibling": dict(self.sibling),
            "doctrine_keys": list(self.doctrine_keys),
            "fabric_stats": dict(self.fabric_stats),
            "evidence": dict(self.evidence),
            "catalog": dict(self.catalog),
            "projections": list(self.projections),
            "metrics": dict(self.metrics),
            "windows": dict(self.windows),
            "checkpoints": dict(self.checkpoints),
        }


def build_audit_pack(service: OmniFabricService, *, full_evidence: bool = True) -> AuditPack:
    status = service.status()
    evidence = (
        evidence_bundle(service.fabric.snapshot_tail())
        if full_evidence
        else {"ok": True, "skipped": True}
    )
    return AuditPack(
        sibling={
            "repo": SIBLING_REPO,
            "path": SIBLING_PATH,
            "module": SIBLING_MODULE,
        },
        doctrine_keys=sorted(DOCTRINE.keys()),
        fabric_stats=dict(status["fabric"]),
        evidence=evidence,
        catalog=dict(status["catalog"]),
        projections=list(status["projections"]),
        metrics=dict(status["metrics"]),
        windows=dict(status["windows"]),
        checkpoints=dict(status["checkpoints"]),
    )
