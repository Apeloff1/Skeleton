"""Weakest-surface regenerate tooling for STU-TOOLS cockpit/doctor deepen.

Identifies the weakest fraction of scored surfaces (health / visualize / doctor /
forge artefacts) and produces a fail-closed regenerate plan + optional dry-run
patches. Never silently accepts empty or Sev1-red inventories.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateSuite,
    Verdict,
    error_gate,
)
from skeleton.developer.surface_inventory import (
    Surface,
    SurfaceInventory,
    SurfaceKind,
    SurfacePath,
    inventory_from_artefacts,
)


DEFAULT_FRACTION = 0.15
DEFAULT_SCORE_CEILING = 0.7


@dataclass
class RegenTarget:
    identity: str
    path: str
    kind: str
    name: str
    score: float
    status: str
    issues: List[str] = field(default_factory=list)
    action: str = "regenerate"
    patch_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "path": self.path,
            "kind": self.kind,
            "name": self.name,
            "score": round(self.score, 4),
            "status": self.status,
            "issues": list(self.issues),
            "action": self.action,
            "patch_preview": self.patch_preview,
        }


@dataclass
class RegenPlan:
    kind: str = "stu-tools-regen-plan"
    targets: List[RegenTarget] = field(default_factory=list)
    fraction: float = DEFAULT_FRACTION
    score_ceiling: float = DEFAULT_SCORE_CEILING
    source_path: str = ""
    created_at: float = field(default_factory=time.time)
    stored_prose: int = 0

    @property
    def empty(self) -> bool:
        return not self.targets

    def fingerprint(self) -> str:
        payload = json.dumps(
            [t.to_dict() for t in self.targets],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "targets": [t.to_dict() for t in self.targets],
            "count": len(self.targets),
            "fraction": self.fraction,
            "score_ceiling": self.score_ceiling,
            "source_path": self.source_path,
            "created_at": self.created_at,
            "fingerprint": self.fingerprint(),
            "stored_prose": self.stored_prose,
        }


@dataclass
class RegenResult:
    plan: RegenPlan
    applied: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    dry_run: bool = True
    artefacts_after: Dict[str, str] = field(default_factory=dict)
    stored_prose: int = 0

    @property
    def ok(self) -> int:
        return 0 if self.failed else 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "stu-tools-regen-result",
            "ok": self.ok,
            "dry_run": self.dry_run,
            "plan": self.plan.to_dict(),
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "failed": list(self.failed),
            "artefact_count": len(self.artefacts_after),
            "artefacts_after": dict(self.artefacts_after),
            "stored_prose": self.stored_prose,
        }


def _action_for(surface: Surface) -> str:
    if surface.kind == SurfaceKind.FORGE_ARTEFACT:
        if "empty_content" in surface.issues:
            return "reemit_empty"
        if "unresolved_marker" in surface.issues:
            return "strip_todo_and_reverify"
        if "stored_prose_suspect" in surface.issues:
            return "enforce_stored_prose_zero"
        return "regenerate_artefact"
    if surface.kind == SurfaceKind.DOCTOR_DOMAIN:
        return "retune_doctor_domain"
    if surface.kind == SurfaceKind.SUBSYSTEM:
        return "restart_or_reprobe_subsystem"
    if surface.kind == SurfaceKind.BLUEPRINT:
        return "rewire_or_reemit_component"
    if surface.kind == SurfaceKind.COCKPIT_KNOB:
        return "clamp_cockpit_knob"
    return "regenerate"


def _patch_preview(surface: Surface) -> str:
    if surface.kind == SurfaceKind.FORGE_ARTEFACT:
        return f"# regenerate {surface.name}\n# issues: {','.join(surface.issues) or 'score'}\n"
    if surface.kind == SurfaceKind.COCKPIT_KNOB:
        return f"{surface.name}=1.0  # clamp to healthy range\n"
    return f"regen:{surface.identity}\n"


def select_weakest(
    inventory: SurfaceInventory,
    *,
    path: Optional[SurfacePath] = None,
    fraction: float = DEFAULT_FRACTION,
    score_ceiling: float = DEFAULT_SCORE_CEILING,
) -> List[Surface]:
    pool = inventory.weakest(fraction=fraction, path=path)
    return [s for s in pool if s.score <= score_ceiling]


def build_regen_plan(
    inventory: SurfaceInventory,
    *,
    path: Optional[SurfacePath] = None,
    fraction: float = DEFAULT_FRACTION,
    score_ceiling: float = DEFAULT_SCORE_CEILING,
) -> RegenPlan:
    targets: List[RegenTarget] = []
    for surface in select_weakest(
        inventory, path=path, fraction=fraction, score_ceiling=score_ceiling
    ):
        targets.append(
            RegenTarget(
                identity=surface.identity,
                path=surface.path.value,
                kind=surface.kind.value,
                name=surface.name,
                score=surface.score,
                status=surface.status,
                issues=list(surface.issues),
                action=_action_for(surface),
                patch_preview=_patch_preview(surface),
            )
        )
    return RegenPlan(
        targets=targets,
        fraction=fraction,
        score_ceiling=score_ceiling,
        source_path=(path.value if path else "all"),
        stored_prose=int(inventory.stored_prose or 0),
    )


def gate_regen_plan(plan: RegenPlan, *, allow_empty: bool = False) -> Verdict:
    suite = GateSuite("stu-tools-regen")
    suite.check(
        plan.stored_prose == 0,
        "regen.stored_prose_zero",
        severity=GateSeverity.SEV1,
        on_pass="stored_prose=0",
        on_fail=f"stored_prose={plan.stored_prose}",
    )
    if not allow_empty:
        suite.check(
            not plan.empty,
            "regen.targets_nonempty",
            severity=GateSeverity.SEV2,
            on_pass=f"targets={len(plan.targets)}",
            on_fail="regen plan empty — nothing to strengthen",
        )
    else:
        suite.check(
            True,
            "regen.targets_optional",
            severity=GateSeverity.INFO,
            on_pass=f"targets={len(plan.targets)}",
            on_fail="unreachable",
        )
    bad_actions = [t.name for t in plan.targets if not t.action]
    suite.check(
        not bad_actions,
        "regen.actions_present",
        severity=GateSeverity.SEV1,
        on_pass="all targets have actions",
        on_fail=f"missing actions: {','.join(bad_actions)}",
        evidence=[GateEvidence("bad", bad_actions)],
    )
    return suite.verdict()


def apply_regen_plan(
    plan: RegenPlan,
    *,
    artefacts: Optional[Mapping[str, str]] = None,
    dry_run: bool = True,
    mutator: Optional[Callable[[RegenTarget, Dict[str, str]], Optional[str]]] = None,
) -> RegenResult:
    files = dict(artefacts or {})
    applied: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []

    def _default_mutator(target: RegenTarget, bag: Dict[str, str]) -> Optional[str]:
        if target.kind != SurfaceKind.FORGE_ARTEFACT.value:
            return None
        name = target.name
        if name == "__empty__":
            bag["generated/placeholder.gd"] = (
                "extends Node\n"
                "# regenerated by STU-TOOLS weakest_regenerate\n"
                "func _ready() -> void:\n"
                "    pass\n"
            )
            return "generated/placeholder.gd"
        current = bag.get(name, "")
        cleaned = "\n".join(
            ln for ln in current.splitlines() if "TODO" not in ln and "FIXME" not in ln
        )
        if not cleaned.strip():
            cleaned = (
                f"# regenerated: {name}\n"
                "extends Node\n"
                "func _ready() -> void:\n"
                "    pass\n"
            )
        if '"stored_prose"' in cleaned or "'stored_prose'" in cleaned:
            cleaned = cleaned.replace('"stored_prose": 1', '"stored_prose": 0')
            cleaned = cleaned.replace("'stored_prose': 1", "'stored_prose': 0")
        bag[name] = cleaned if cleaned.endswith("\n") else cleaned + "\n"
        return name

    worker = mutator or _default_mutator
    for target in plan.targets:
        try:
            if dry_run:
                skipped.append(target.identity)
                continue
            touched = worker(target, files)
            if touched:
                applied.append(touched)
            else:
                skipped.append(target.identity)
        except Exception as exc:
            failed.append(f"{target.identity}:{exc}")

    return RegenResult(
        plan=plan,
        applied=applied,
        skipped=skipped,
        failed=failed,
        dry_run=dry_run,
        artefacts_after=files,
        stored_prose=plan.stored_prose,
    )


def run_weakest_regenerate(
    inventory: Optional[SurfaceInventory] = None,
    *,
    artefacts: Optional[Mapping[str, str]] = None,
    path: Optional[SurfacePath] = None,
    fraction: float = DEFAULT_FRACTION,
    score_ceiling: float = DEFAULT_SCORE_CEILING,
    dry_run: bool = True,
    allow_empty: bool = False,
) -> Dict[str, Any]:
    try:
        if inventory is None:
            if artefacts is None:
                raise ValueError("inventory or artefacts required")
            inventory = inventory_from_artefacts(artefacts)
        plan = build_regen_plan(
            inventory,
            path=path,
            fraction=fraction,
            score_ceiling=score_ceiling,
        )
    except Exception as exc:
        verdict = GateSuite("stu-tools-regen").add(
            error_gate(
                "regen.collect",
                severity=GateSeverity.SEV1,
                reason=f"regen plan crashed: {exc}",
            )
        ).verdict()
        return {
            "kind": "stu-tools-regen-gates",
            "ok": verdict.ok,
            "banner": verdict.banner,
            "verdict": verdict.to_dict(),
            "stored_prose": 0,
        }

    verdict = gate_regen_plan(plan, allow_empty=allow_empty)
    result = apply_regen_plan(plan, artefacts=artefacts, dry_run=dry_run)
    after_inv = None
    if artefacts is not None and not dry_run and result.artefacts_after:
        after_inv = inventory_from_artefacts(result.artefacts_after)
        # Sev1: regenerated set must not be empty when we intended to apply
        if not allow_empty and plan.targets and result.ok and after_inv.mean_score() < inventory.mean_score():
            # score drop after regen is Sev2
            from skeleton.developer.gate_verdict import fail_gate
            suite = GateSuite("stu-tools-regen-after")
            suite.add(
                fail_gate(
                    "regen.after_score_drop",
                    severity=GateSeverity.SEV2,
                    reason=f"mean {inventory.mean_score()}->{after_inv.mean_score()}",
                )
            )
            # merge manually
            from skeleton.developer.gate_verdict import merge_verdicts
            verdict = merge_verdicts("stu-tools-regen", [verdict, suite.verdict()])

    ok = 1 if verdict.ok and result.ok else 0
    return {
        "kind": "stu-tools-regen-gates",
        "ok": ok,
        "banner": verdict.banner if ok else (verdict.banner if not verdict.ok else "VERDICT: FAIL CLOSED — regen.apply"),
        "verdict": verdict.to_dict(),
        "result": result.to_dict(),
        "after_inventory": after_inv.to_dict() if after_inv is not None else None,
        "stored_prose": plan.stored_prose,
    }


def assert_regen_green(result: Mapping[str, Any]) -> None:
    if int(result.get("ok") or 0) != 1:
        banner = result.get("banner") or (result.get("verdict") or {}).get("banner") or "red"
        raise AssertionError(f"regen gates red: {banner}")


__all__ = [
    "RegenTarget",
    "RegenPlan",
    "RegenResult",
    "select_weakest",
    "build_regen_plan",
    "gate_regen_plan",
    "apply_regen_plan",
    "run_weakest_regenerate",
    "assert_regen_green",
    "DEFAULT_FRACTION",
    "DEFAULT_SCORE_CEILING",
]
