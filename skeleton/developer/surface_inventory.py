"""Inventory of STU-TOOLS surfaces for health / visualize / doctor paths.

Surfaces are scored units (subsystem handles, blueprint nodes, doctor alert
domains, cockpit knobs, forge artefacts). The inventory is deterministic and
fail-closed when required surfaces are missing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


class SurfaceKind(str, Enum):
    SUBSYSTEM = "subsystem"
    BLUEPRINT = "blueprint"
    DOCTOR_DOMAIN = "doctor_domain"
    COCKPIT_KNOB = "cockpit_knob"
    FORGE_ARTEFACT = "forge_artefact"
    GATE = "gate"
    REPORT = "report"


class SurfacePath(str, Enum):
    HEALTH = "health"
    VISUALIZE = "visualize"
    DOCTOR = "doctor"
    COCKPIT = "cockpit"
    WEAKEST = "weakest"
    PIPELINE = "pipeline"


REQUIRED_HEALTH_SURFACES = (
    "kernel",
    "memory",
    "intelligence",
    "swarm",
    "resilience",
    "observability",
    "cortex",
)

REQUIRED_DOCTOR_DOMAINS = (
    "repair",
    "kv_cache",
    "policy",
    "resilience",
    "health",
    "audit",
    "dashboard",
)

REQUIRED_COCKPIT_KNOBS = (
    "speed_mul",
    "heat_mul",
    "collapse_mul",
)

REQUIRED_VISUALIZE_FIELDS = (
    "components",
    "wires",
    "name",
)


@dataclass
class Surface:
    """A scored unit on a STU-TOOLS path."""

    path: SurfacePath
    kind: SurfaceKind
    name: str
    score: float = 1.0
    status: str = "healthy"
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    required: bool = False
    parent: str = ""
    tags: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.score = _clamp01(self.score)
        if self.issues and self.status == "healthy":
            self.status = "degraded"

    @property
    def identity(self) -> str:
        return f"{self.path.value}:{self.kind.value}:{self.name}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path.value,
            "kind": self.kind.value,
            "name": self.name,
            "score": round(self.score, 4),
            "status": self.status,
            "issues": list(self.issues),
            "metrics": dict(self.metrics),
            "required": self.required,
            "parent": self.parent,
            "tags": list(self.tags),
            "identity": self.identity,
        }


def _clamp01(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def status_score(status: str) -> float:
    return {
        "healthy": 1.0,
        "ok": 1.0,
        "passed": 1.0,
        "degraded": 0.55,
        "warning": 0.55,
        "unknown": 0.4,
        "failed": 0.1,
        "critical": 0.05,
        "error": 0.0,
        "missing": 0.0,
    }.get(str(status).lower(), 0.35)


def score_from_metrics(metrics: Mapping[str, Any], *, base: float = 1.0) -> float:
    """Derive a 0..1 score from common metric keys."""
    score = _clamp01(base)
    if not metrics:
        return score
    if "healthy" in metrics:
        score = min(score, 1.0 if metrics["healthy"] else 0.2)
    if "hit_rate" in metrics:
        try:
            score = min(score, max(0.0, float(metrics["hit_rate"])))
        except (TypeError, ValueError):
            score = min(score, 0.3)
    if "success_rate" in metrics:
        try:
            score = min(score, max(0.0, float(metrics["success_rate"])))
        except (TypeError, ValueError):
            score = min(score, 0.3)
    if "error_ratio" in metrics:
        try:
            er = float(metrics["error_ratio"])
            score = min(score, max(0.0, 1.0 - er))
        except (TypeError, ValueError):
            score = min(score, 0.4)
    if "pressure" in metrics:
        try:
            pressure = float(metrics["pressure"])
            score = min(score, max(0.0, 1.0 - pressure))
        except (TypeError, ValueError):
            score = min(score, 0.4)
    if "issue_count" in metrics:
        try:
            n = int(metrics["issue_count"])
            score = min(score, max(0.0, 1.0 - 0.08 * n))
        except (TypeError, ValueError):
            pass
    return _clamp01(score)


@dataclass
class SurfaceInventory:
    """Deterministic inventory of surfaces across STU-TOOLS paths."""

    surfaces: List[Surface] = field(default_factory=list)
    stored_prose: int = 0

    def add(self, surface: Surface) -> None:
        self.surfaces.append(surface)

    def extend(self, surfaces: Iterable[Surface]) -> None:
        self.surfaces.extend(surfaces)

    def by_path(self, path: SurfacePath) -> List[Surface]:
        return [s for s in self.surfaces if s.path == path]

    def by_kind(self, kind: SurfaceKind) -> List[Surface]:
        return [s for s in self.surfaces if s.kind == kind]

    def required_missing(self, path: SurfacePath) -> List[str]:
        present = {s.name for s in self.by_path(path)}
        required = required_names_for(path)
        return [name for name in required if name not in present]

    def weakest(self, *, fraction: float = 0.15, path: Optional[SurfacePath] = None) -> List[Surface]:
        """Return the weakest fraction (default 15%) of surfaces, sorted ascending."""
        pool = list(self.surfaces if path is None else self.by_path(path))
        if not pool:
            return []
        frac = _clamp01(fraction)
        if frac < 0.10:
            frac = 0.10
        if frac > 0.20:
            frac = 0.20
        ordered = sorted(pool, key=lambda s: (s.score, s.name))
        n = max(1, int(round(len(ordered) * frac)))
        n = min(n, len(ordered))
        return ordered[:n]

    def mean_score(self, path: Optional[SurfacePath] = None) -> float:
        pool = list(self.surfaces if path is None else self.by_path(path))
        if not pool:
            return 0.0
        return round(sum(s.score for s in pool) / len(pool), 4)

    def fingerprint(self) -> str:
        payload = json.dumps(
            [s.to_dict() for s in sorted(self.surfaces, key=lambda x: x.identity)],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-surface-inventory",
            "count": len(self.surfaces),
            "mean_score": self.mean_score(),
            "by_path": {
                p.value: len(self.by_path(p)) for p in SurfacePath
            },
            "missing": {
                p.value: self.required_missing(p) for p in SurfacePath
            },
            "surfaces": [s.to_dict() for s in self.surfaces],
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


def required_names_for(path: SurfacePath) -> Tuple[str, ...]:
    if path == SurfacePath.HEALTH:
        return REQUIRED_HEALTH_SURFACES
    if path == SurfacePath.DOCTOR:
        return REQUIRED_DOCTOR_DOMAINS
    if path == SurfacePath.COCKPIT:
        return REQUIRED_COCKPIT_KNOBS
    if path == SurfacePath.VISUALIZE:
        return REQUIRED_VISUALIZE_FIELDS
    return ()


def inventory_from_health_summary(summary: Mapping[str, Any]) -> SurfaceInventory:
    """Build inventory from a SubsystemExplorer.summary()-shaped payload."""
    inv = SurfaceInventory()
    cards = summary.get("cards") or []
    seen = set()
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name") or "unknown")
        seen.add(name)
        status = str(card.get("status") or "unknown")
        metrics = dict(card.get("metrics") or {})
        score = score_from_metrics(metrics, base=status_score(status))
        issues: List[str] = []
        if status in {"failed", "critical", "error"}:
            issues.append(f"status:{status}")
        if status == "degraded":
            issues.append("status:degraded")
        inv.add(
            Surface(
                path=SurfacePath.HEALTH,
                kind=SurfaceKind.SUBSYSTEM,
                name=name,
                score=score,
                status=status,
                issues=issues,
                metrics=metrics,
                required=name in REQUIRED_HEALTH_SURFACES or str(card.get("phase") or "") in REQUIRED_HEALTH_SURFACES,
                parent=str(card.get("phase") or ""),
                tags=("health",),
            )
        )
    # Phase-level required surfaces when cards are handle-granular
    phases = {str(c.get("phase") or "") for c in cards if isinstance(c, Mapping)}
    for req in REQUIRED_HEALTH_SURFACES:
        if req in seen or req in phases:
            if req not in seen:
                inv.add(
                    Surface(
                        path=SurfacePath.HEALTH,
                        kind=SurfaceKind.SUBSYSTEM,
                        name=req,
                        score=0.85 if req in phases else 0.0,
                        status="healthy" if req in phases else "missing",
                        issues=[] if req in phases else ["required_surface_missing"],
                        required=True,
                        tags=("health", "required"),
                    )
                )
        else:
            inv.add(
                Surface(
                    path=SurfacePath.HEALTH,
                    kind=SurfaceKind.SUBSYSTEM,
                    name=req,
                    score=0.0,
                    status="missing",
                    issues=["required_surface_missing"],
                    required=True,
                    tags=("health", "required"),
                )
            )
    return inv


def inventory_from_doctor_card(card: Mapping[str, Any]) -> SurfaceInventory:
    """Build inventory from an organism doctor_card()-shaped payload."""
    inv = SurfaceInventory()
    alerts = card.get("alerts") or []
    alert_by_sub: Dict[str, List[Mapping[str, Any]]] = {}
    for alert in alerts:
        if not isinstance(alert, Mapping):
            continue
        sub = str(alert.get("subsystem") or "unknown")
        alert_by_sub.setdefault(sub, []).append(alert)

    domain_payloads = {
        "repair": card.get("repair_effectiveness") or card.get("error_summary") or {},
        "kv_cache": card.get("kv_cache") or {},
        "policy": card.get("policy") or {},
        "resilience": card.get("circuit") or card.get("load_shedder") or {},
        "health": card.get("health") or {},
        "audit": card.get("audit_integrity") or {},
        "dashboard": card.get("dashboard") or {},
    }

    for domain in REQUIRED_DOCTOR_DOMAINS:
        payload = domain_payloads.get(domain) or {}
        domain_alerts = alert_by_sub.get(domain, [])
        severity_penalty = 0.0
        issues: List[str] = []
        for a in domain_alerts:
            sev = str(a.get("severity") or "info").lower()
            issues.append(f"alert:{sev}:{a.get('message', '')[:80]}")
            if sev == "critical":
                severity_penalty += 0.45
            elif sev == "warning":
                severity_penalty += 0.25
            else:
                severity_penalty += 0.1
        base = 1.0 - min(0.95, severity_penalty)
        score = score_from_metrics(payload if isinstance(payload, Mapping) else {}, base=base)
        status = "healthy"
        if any(str(a.get("severity")) == "critical" for a in domain_alerts):
            status = "critical"
        elif domain_alerts:
            status = "degraded"
        elif score < 0.5:
            status = "degraded"
        inv.add(
            Surface(
                path=SurfacePath.DOCTOR,
                kind=SurfaceKind.DOCTOR_DOMAIN,
                name=domain,
                score=score,
                status=status,
                issues=issues,
                metrics=dict(payload) if isinstance(payload, Mapping) else {},
                required=True,
                tags=("doctor", "required"),
            )
        )
    return inv


def inventory_from_blueprint(topology: Mapping[str, Any], *, name: str = "") -> SurfaceInventory:
    """Build inventory from a blueprint topology dict."""
    inv = SurfaceInventory()
    bp_name = name or str(topology.get("name") or topology.get("blueprint") or "unnamed")
    components = topology.get("components") or {}
    wires = topology.get("wires") or []
    if isinstance(components, Mapping):
        comp_items = list(components.items())
    elif isinstance(components, list):
        comp_items = [(str(c.get("id") or c.get("name") or i), c) for i, c in enumerate(components) if isinstance(c, Mapping)]
    else:
        comp_items = []

    for field_name in REQUIRED_VISUALIZE_FIELDS:
        present = field_name in topology or (field_name == "name" and bool(bp_name))
        if field_name == "components":
            present = present or bool(comp_items)
        if field_name == "wires":
            present = present or isinstance(wires, list)
        inv.add(
            Surface(
                path=SurfacePath.VISUALIZE,
                kind=SurfaceKind.BLUEPRINT,
                name=field_name,
                score=1.0 if present else 0.0,
                status="healthy" if present else "missing",
                issues=[] if present else ["required_field_missing"],
                required=True,
                parent=bp_name,
                tags=("visualize", "required"),
            )
        )

    for cid, comp in comp_items:
        if isinstance(comp, Mapping):
            kind = str(comp.get("kind") or "component")
            ports = comp.get("ports") or []
            port_n = len(ports) if isinstance(ports, (list, tuple)) else 0
            score = 1.0 if port_n > 0 else 0.5
            issues = [] if port_n > 0 else ["no_ports"]
        else:
            kind = "component"
            score = 0.4
            issues = ["opaque_component"]
        inv.add(
            Surface(
                path=SurfacePath.VISUALIZE,
                kind=SurfaceKind.BLUEPRINT,
                name=str(cid),
                score=score,
                status="healthy" if score >= 0.7 else "degraded",
                issues=issues,
                metrics={"kind": kind},
                parent=bp_name,
                tags=("visualize", "component"),
            )
        )

    wire_n = len(wires) if isinstance(wires, list) else 0
    inv.add(
        Surface(
            path=SurfacePath.VISUALIZE,
            kind=SurfaceKind.BLUEPRINT,
            name=f"{bp_name}::wires",
            score=1.0 if wire_n > 0 else 0.35,
            status="healthy" if wire_n > 0 else "degraded",
            issues=[] if wire_n > 0 else ["no_wires"],
            metrics={"wire_count": wire_n},
            parent=bp_name,
            tags=("visualize", "wires"),
        )
    )
    return inv


def inventory_from_cockpit(knobs: Mapping[str, Any]) -> SurfaceInventory:
    inv = SurfaceInventory()
    for knob in REQUIRED_COCKPIT_KNOBS:
        raw = knobs.get(knob)
        try:
            value = float(raw if raw is not None else 1.0)
            ok = 0.5 <= value <= 2.0
            score = 1.0 if ok else 0.2
            issues = [] if ok else [f"out_of_range:{value}"]
        except (TypeError, ValueError):
            value = None
            score = 0.0
            issues = ["non_numeric"]
            ok = False
        inv.add(
            Surface(
                path=SurfacePath.COCKPIT,
                kind=SurfaceKind.COCKPIT_KNOB,
                name=knob,
                score=score,
                status="healthy" if ok else "failed",
                issues=issues,
                metrics={"value": value},
                required=True,
                tags=("cockpit", "required"),
            )
        )
    # stored_prose must stay 0
    prose = knobs.get("stored_prose", 0)
    try:
        prose_i = int(prose)
    except (TypeError, ValueError):
        prose_i = 1
    inv.add(
        Surface(
            path=SurfacePath.COCKPIT,
            kind=SurfaceKind.COCKPIT_KNOB,
            name="stored_prose",
            score=1.0 if prose_i == 0 else 0.0,
            status="healthy" if prose_i == 0 else "critical",
            issues=[] if prose_i == 0 else ["stored_prose_nonzero"],
            metrics={"value": prose_i},
            required=True,
            tags=("cockpit", "law"),
        )
    )
    inv.stored_prose = prose_i
    return inv


def inventory_from_artefacts(files: Mapping[str, str]) -> SurfaceInventory:
    """Score forge artefact files — used by weakest-regenerate."""
    inv = SurfaceInventory()
    if not files:
        inv.add(
            Surface(
                path=SurfacePath.WEAKEST,
                kind=SurfaceKind.FORGE_ARTEFACT,
                name="__empty__",
                score=0.0,
                status="failed",
                issues=["empty_artefact_set"],
                required=True,
                tags=("weakest",),
            )
        )
        return inv
    for path, content in sorted(files.items()):
        text = content if isinstance(content, str) else str(content)
        issues: List[str] = []
        score = 1.0
        if not text.strip():
            issues.append("empty_content")
            score = 0.0
        if "TODO" in text or "FIXME" in text:
            issues.append("unresolved_marker")
            score = min(score, 0.45)
        if "stored_prose" in text and '"stored_prose": 0' not in text and "'stored_prose': 0" not in text:
            # soft signal only for artefacts that embed the law field incorrectly
            if '"stored_prose":' in text or "'stored_prose':" in text:
                issues.append("stored_prose_suspect")
                score = min(score, 0.3)
        lines = text.splitlines()
        if len(lines) < 2 and path.endswith((".gd", ".py", ".json")):
            issues.append("too_short")
            score = min(score, 0.4)
        # density heuristic: comment/noise ratio
        noise = sum(1 for ln in lines if ln.strip().startswith("#") or not ln.strip())
        if lines and noise / len(lines) > 0.7:
            issues.append("high_noise_ratio")
            score = min(score, 0.5)
        inv.add(
            Surface(
                path=SurfacePath.WEAKEST,
                kind=SurfaceKind.FORGE_ARTEFACT,
                name=path,
                score=_clamp01(score),
                status="healthy" if score >= 0.7 else ("failed" if score < 0.3 else "degraded"),
                issues=issues,
                metrics={"bytes": len(text.encode("utf-8")), "lines": len(lines)},
                required=False,
                tags=("weakest", "artefact"),
            )
        )
    return inv


def merge_inventories(*inventories: SurfaceInventory) -> SurfaceInventory:
    out = SurfaceInventory()
    prose = 0
    for inv in inventories:
        out.extend(inv.surfaces)
        prose = max(prose, int(inv.stored_prose or 0))
    out.stored_prose = prose
    return out


__all__ = [
    "SurfaceKind",
    "SurfacePath",
    "Surface",
    "SurfaceInventory",
    "REQUIRED_HEALTH_SURFACES",
    "REQUIRED_DOCTOR_DOMAINS",
    "REQUIRED_COCKPIT_KNOBS",
    "REQUIRED_VISUALIZE_FIELDS",
    "status_score",
    "score_from_metrics",
    "required_names_for",
    "inventory_from_health_summary",
    "inventory_from_doctor_card",
    "inventory_from_blueprint",
    "inventory_from_cockpit",
    "inventory_from_artefacts",
    "merge_inventories",
]
