"""Read-only, evidence-bound project completion status for the canonical AI product.

Project planning maturity, capability readiness, enterprise qualification, and
release acceptance are distinct dimensions. This module never infers live
functional readiness from a checkbox, source-file presence, or a stale index.
No network access, model execution, authority promotion, or state mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import json
import re
from typing import Any, Mapping


class CompletionStatusError(ValueError):
    """Malformed or missing project evidence; refuse a completion verdict."""


_SOURCE_PATHS = (
    "machine/ai_master_plan.json",
    "machine/ai_build_accountability.json",
)
_REQUIRED_JSON = (
    "machine/ai_master_plan.json",
    "machine/ai_masterplan_parse_index.json",
    "machine/ai_capabilities.json",
    "machine/ai_app_construction.json",
    "machine/ai_implementation_handoff.json",
    "machine/ai_closure_evidence.json",
    "machine/enterprise_ai_superiority.json",
)
_GIT_BLOB_RE = re.compile(r"^[0-9a-f]{40}$")
_IMPLEMENTED = frozenset({"verified", "hardened", "production"})
_ENTERPRISE_QUALIFIED = frozenset({"enterprise_qualified", "superior"})
_PRODUCT_COMPLETE = frozenset({"complete", "verified", "production"})


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompletionStatusError("duplicate JSON field: " + key)
        result[key] = value
    return result


def _read_json(root: Path, path: str) -> dict[str, Any]:
    file_path = root / path
    try:
        size = file_path.stat().st_size
        if size > 16_000_000:
            raise CompletionStatusError(f"{path}: JSON exceeds audit budget")
        with file_path.open("r", encoding="utf-8") as source:
            data = json.load(source, object_pairs_hook=_unique_pairs,
                             parse_constant=lambda value: (_ for _ in ()).throw(
                                 CompletionStatusError("nonfinite JSON value")
                             ))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompletionStatusError(f"{path}: evidence not readable") from exc
    if not isinstance(data, dict):
        raise CompletionStatusError(f"{path}: expected JSON object")
    return data


def _records(obj: Mapping[str, Any], field: str, owner: str,
             *, id_field: str) -> tuple[dict[str, Any], ...]:
    raw = obj.get(field)
    if not isinstance(raw, list):
        raise CompletionStatusError(f"{owner}.{field}: expected list")
    result = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise CompletionStatusError(f"{owner}.{field}: invalid record")
        key = item.get(id_field)
        if not isinstance(key, str) or not key or key in seen:
            raise CompletionStatusError(f"{owner}.{field}: invalid/duplicate {id_field}")
        seen.add(key)
        result.append(item)
    return tuple(result)


def _git_blob_sha(path: Path) -> str:
    """Compute exact Git blob SHA without shelling out or trusting an index."""
    try:
        size = path.stat().st_size
        hasher = sha1(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as source:
            while chunk := source.read(1 << 20):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError as exc:
        raise CompletionStatusError(f"missing/unreadable index source: {path.name}") from exc


def _count_by(records: tuple[dict[str, Any], ...], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        state = record.get(field)
        if not isinstance(state, str) or not state:
            raise CompletionStatusError("missing classification " + field)
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class CompletionStatus:
    """Structured status, never an automatic completion/signoff receipt."""

    plan_volume_total: int
    plan_mature: int
    plan_statuses: Mapping[str, int]
    enterprise_qualified: int
    enterprise_states: Mapping[str, int]
    product_capability_total: int
    product_complete: int
    product_states: Mapping[str, int]
    pending_capabilities: tuple[str, ...]
    construction_gap_total: int
    construction_gaps_closed: int
    implementation_handoff_total: int
    implementation_handoffs_closed: int
    closure_evidence_total: int
    closure_evidence_closed: int
    architecture_plane_total: int
    architecture_planes_present: int
    signature_index_fresh: bool
    signed_plan_volumes: int | None
    index_source_bindings: Mapping[str, bool]
    blockers: tuple[str, ...]

    @property
    def plan_percent(self) -> float:
        return round(100 * self.plan_mature / self.plan_volume_total, 2) if self.plan_volume_total else 0.0

    @property
    def product_percent(self) -> float:
        return round(100 * self.product_complete / self.product_capability_total, 2) if self.product_capability_total else 0.0

    @property
    def enterprise_percent(self) -> float:
        return round(100 * self.enterprise_qualified / self.plan_volume_total, 2) if self.plan_volume_total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "skeleton.ai.project-status.v1",
            "plan": {"mature": self.plan_mature, "total": self.plan_volume_total,
                     "percent": self.plan_percent, "states": dict(self.plan_statuses)},
            "enterprise": {"qualified": self.enterprise_qualified,
                           "total": self.plan_volume_total,
                           "percent": self.enterprise_percent,
                           "states": dict(self.enterprise_states)},
            "product": {"complete": self.product_complete,
                        "total": self.product_capability_total,
                        "percent": self.product_percent,
                        "states": dict(self.product_states),
                        "pending": list(self.pending_capabilities)},
            "construction": {
                "closed_gaps": self.construction_gaps_closed,
                "total_gaps": self.construction_gap_total,
                "closed_handoffs": self.implementation_handoffs_closed,
                "total_handoffs": self.implementation_handoff_total,
                "closed_evidence_entries": self.closure_evidence_closed,
                "total_evidence_entries": self.closure_evidence_total,
                "present_planes": self.architecture_planes_present,
                "total_planes": self.architecture_plane_total,
            },
            "signatures": {
                "index_fresh": self.signature_index_fresh,
                "current_signed_volumes": self.signed_plan_volumes,
                "source_matches": dict(self.index_source_bindings),
            },
            "release_ready": False,
            "release_gate": "live exact-head production acceptance is not evaluated by this offline report",
            "overall_percent": None,
            "overall_percent_reason": "no validated cross-domain weighting or live release acceptance",
            "blockers": list(self.blockers),
        }


def inspect_project(root: str | Path) -> CompletionStatus:
    """Inspect canonical machine authorities and exact byte identities."""
    repo_root = Path(root).resolve()
    authorities = {name: _read_json(repo_root, name) for name in _REQUIRED_JSON}
    master = authorities["machine/ai_master_plan.json"]
    index = authorities["machine/ai_masterplan_parse_index.json"]
    capability_registry = authorities["machine/ai_capabilities.json"]
    construction = authorities["machine/ai_app_construction.json"]
    handoff = authorities["machine/ai_implementation_handoff.json"]
    evidence = authorities["machine/ai_closure_evidence.json"]
    enterprise = authorities["machine/enterprise_ai_superiority.json"]

    volumes = _records(master, "volumes", "masterplan", id_field="key")
    capabilities = _records(capability_registry, "capabilities", "capabilities", id_field="capability_id")
    gaps = _records(construction, "gap_register", "construction", id_field="id")
    handoffs = _records(handoff, "entries", "handoff", id_field="gap")
    evidences = _records(evidence, "entries", "evidence", id_field="gap")
    planes = _records(construction, "planes", "construction", id_field="id")

    plan_states = _count_by(volumes, "implementation_status")
    enterprise_states = _count_by(volumes, "enterprise_grade_state")
    product_states = _count_by(capabilities, "implementation_state")
    plan_mature = sum(plan_states.get(state, 0) for state in _IMPLEMENTED)
    qualified = sum(enterprise_states.get(state, 0) for state in _ENTERPRISE_QUALIFIED)
    product_complete = sum(product_states.get(state, 0) for state in _PRODUCT_COMPLETE)
    pending = tuple(sorted(c["capability_id"] for c in capabilities
                           if c["implementation_state"] not in _PRODUCT_COMPLETE))
    closed_gaps = sum(g.get("status") == "closed" for g in gaps)
    closed_handoffs = sum(e.get("implementation_status") == "closed" for e in handoffs)
    closed_evidence = sum(e.get("closure_decision") == "closed" for e in evidences)
    present_planes = sum(p.get("state") == "present" for p in planes)

    grade_states = enterprise.get("grade_model", {}).get("states")
    if not isinstance(grade_states, list) or not _ENTERPRISE_QUALIFIED.issubset(grade_states):
        raise CompletionStatusError("enterprise grade authority is malformed")
    if set(enterprise_states) - set(grade_states):
        raise CompletionStatusError("unknown enterprise maturity state")

    declared_sources = index.get("sources")
    if not isinstance(declared_sources, dict):
        raise CompletionStatusError("signature index sources missing")
    source_bindings = {}
    for path in _SOURCE_PATHS:
        expected = declared_sources.get(path)
        expected_sha = expected.get("git_blob_sha") if isinstance(expected, dict) else None
        source_bindings[path] = bool(
            isinstance(expected_sha, str)
            and _GIT_BLOB_RE.fullmatch(expected_sha)
            and expected_sha == _git_blob_sha(repo_root / path)
        )
    index_fresh = all(source_bindings.values())
    signed = None
    if index_fresh:
        summary = index.get("volume_summary")
        if not isinstance(summary, dict) or summary.get("total") != len(volumes):
            raise CompletionStatusError("signature index volume count mismatch")
        complete_count = summary.get("complete")
        if type(complete_count) is not int or not 0 <= complete_count <= len(volumes):
            raise CompletionStatusError("signature index completion count invalid")
        signed = complete_count

    blockers = []
    if plan_mature != len(volumes):
        blockers.append("some masterplan volumes lack verified/hardened implementation")
    if not index_fresh:
        blockers.append("signature parse index is stale against canonical Git blobs")
    elif signed != len(volumes):
        blockers.append("some masterplan volumes lack current dual signatures")
    if product_complete != len(capabilities):
        blockers.append("one or more declared AI product capabilities remain incomplete")
    if qualified != len(volumes):
        blockers.append("enterprise qualification is not complete on all masterplan volumes")
    if closed_gaps != len(gaps) or closed_handoffs != len(handoffs) or closed_evidence != len(evidences):
        blockers.append("canonical construction/closure gap evidence is open")
    if present_planes != len(planes):
        blockers.append("architecture planes are not all present")
    blockers.append("exact-head live application acceptance and release verification are unassessed")

    return CompletionStatus(
        len(volumes), plan_mature, plan_states, qualified, enterprise_states,
        len(capabilities), product_complete, product_states, pending,
        len(gaps), closed_gaps, len(handoffs), closed_handoffs,
        len(evidences), closed_evidence, len(planes), present_planes,
        index_fresh, signed, source_bindings, tuple(blockers),
    )


__all__ = ["CompletionStatus", "CompletionStatusError", "inspect_project"]
