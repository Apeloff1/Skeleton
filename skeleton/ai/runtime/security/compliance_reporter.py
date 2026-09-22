"""Compliance reporter — aggregated regulatory posture reports.

Aggregates evidence from RBAC, audit log, encryption, access reviews,
secret rotation, and vulnerability scans into a compliance posture
per framework (SOC2-lite, ISO-lite, internal). Reports control
coverage, evidence freshness, and gaps requiring remediation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Control:
    control_id: str
    framework: str
    description: str
    evidence_fn: Callable[[], bool]
    last_evidence_ns: int = 0
    satisfied: bool = False
    max_age_s: float = 86400.0 * 30


class ComplianceReporter:
    """Framework-mapped control coverage reporting."""

    def __init__(self):
        self._controls: Dict[str, Control] = {}
        self._reports: List[Dict[str, Any]] = []

    def add_control(self, control_id: str, framework: str, description: str,
                    evidence_fn: Callable[[], bool],
                    max_age_s: float = 86400.0 * 30) -> Control:
        c = Control(control_id=control_id, framework=framework, description=description,
                    evidence_fn=evidence_fn, max_age_s=max_age_s)
        self._controls[control_id] = c
        return c

    def _seed_defaults(self, checks: Dict[str, Callable[[], bool]]) -> None:
        for cid, (framework, desc) in {
            "AC-1": ("SOC2-lite", "RBAC roles defined with least privilege"),
            "AC-2": ("SOC2-lite", "Access reviews conducted on schedule"),
            "AU-1": ("SOC2-lite", "Audit logging enabled and integrity verified"),
            "SC-1": ("SOC2-lite", "Secrets encrypted at rest"),
            "SC-2": ("SOC2-lite", "Secrets rotated within policy window"),
            "CM-1": ("ISO-lite", "Configuration changes tracked and reviewable"),
            "OP-1": ("ISO-lite", "Backups verified restorable within RPO"),
            "IR-1": ("ISO-lite", "Incident response process with postmortems"),
        }.items():
            if cid in checks:
                self.add_control(cid, framework, desc, checks[cid])

    def evaluate(self) -> Dict[str, Any]:
        now = time.time_ns()
        for control in self._controls.values():
            try:
                control.satisfied = bool(control.evidence_fn())
            except Exception:  # noqa: BLE001
                control.satisfied = False
            if control.satisfied:
                control.last_evidence_ns = now
        report = self._build_report()
        self._reports.append(report)
        return report

    def _build_report(self) -> Dict[str, Any]:
        now = time.time_ns()
        by_framework: Dict[str, Dict[str, Any]] = {}
        for c in self._controls.values():
            fw = by_framework.setdefault(c.framework, {"total": 0, "satisfied": 0, "stale": 0, "gaps": []})
            fw["total"] += 1
            fresh = c.last_evidence_ns and (now - c.last_evidence_ns) / 1e9 <= c.max_age_s
            if c.satisfied:
                fw["satisfied"] += 1
            else:
                fw["gaps"].append({"control": c.control_id, "description": c.description})
            if c.satisfied and not fresh:
                fw["stale"] += 1
        overall = {
            "timestamp_ns": now,
            "frameworks": by_framework,
            "overall_coverage": round(
                sum(f["satisfied"] for f in by_framework.values()) /
                max(1, sum(f["total"] for f in by_framework.values())), 3),
        }
        return overall

    def gaps(self, framework: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for c in self._controls.values():
            if framework and c.framework != framework:
                continue
            if not c.satisfied:
                out.append({"control": c.control_id, "framework": c.framework, "description": c.description})
        return out

    def card(self) -> Dict[str, Any]:
        latest = self._reports[-1] if self._reports else None
        return {
            "kind": "compliance-card",
            "controls": len(self._controls),
            "reports_run": len(self._reports),
            "latest_coverage": latest["overall_coverage"] if latest else None,
            "open_gaps": len(self.gaps()),
        }
