"""B081: Dependabot/security intelligence feed -> repo notes with severity, owner, validation."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._core import ContractError, require, require_keys, require_str, verdict

SEVERITIES = ("critical", "high", "medium", "low")
VALIDATION_BY_SEVERITY = {
    "critical": ("unit", "integration", "security_review"),
    "high": ("unit", "integration"),
    "medium": ("unit",),
    "low": ("unit",),
}


def normalize_alert(alert: Mapping[str, Any], owners: Mapping[str, str]) -> dict[str, Any]:
    require_keys(alert, ("id", "package", "severity", "manifest"), "alert")
    sev = str(alert["severity"]).lower()
    require(sev in SEVERITIES, f"unknown severity {alert['severity']!r}")
    manifest = require_str(alert["manifest"], "manifest")
    owner = _owner_for(manifest, owners)
    return {
        "id": require_str(str(alert["id"]), "id"),
        "package": require_str(alert["package"], "package"),
        "severity": sev,
        "manifest": manifest,
        "owner": owner,
        "validation": list(VALIDATION_BY_SEVERITY[sev]),
    }


def _owner_for(path: str, owners: Mapping[str, str]) -> str:
    best = ""
    for prefix in owners:
        if path.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    if not best:
        raise ContractError(f"no owner for {path}")
    return owners[best]


def build_feed(alerts: Sequence[Mapping[str, Any]], owners: Mapping[str, str]) -> list[dict[str, Any]]:
    notes = [normalize_alert(a, owners) for a in alerts]
    ids = [n["id"] for n in notes]
    require(len(ids) == len(set(ids)), "duplicate alert ids")
    return sorted(notes, key=lambda n: (SEVERITIES.index(n["severity"]), n["package"], n["id"]))


def evaluate(alerts: Sequence[Mapping[str, Any]], owners: Mapping[str, str]):
    findings: list[str] = []
    try:
        feed = build_feed(alerts, owners)
    except ContractError as exc:
        return verdict("B081", [f"feed:{exc}"], notes=0)
    open_critical = sum(1 for n in feed if n["severity"] == "critical")
    if open_critical:
        findings.append(f"open_critical:{open_critical}")
    return verdict("B081", findings, notes=len(feed), open_critical=open_critical)
