"""skeleton/gameforge/conductor.py

The GameForge 7-step conductor: vision -> snowball -> prototype -> mass_forge
-> world -> cockpit -> export. Each step is era-bound, receipt-chained and
fail-closed; any ``GameForgeError`` halts the run and no manifest is emitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from . import steps as S
from .eras import EraBinding, EraRegistry
from .errors import GameForgeError, InputError, IntegrityError, StepOrderError
from .manifest import Manifest, ReceiptLog, build_manifest, digest
from .plans import STEPS, VisionRequest


@dataclass
class ConductorConfig:
    budget_bytes: int = 1_000_000
    regions: int = 5
    target: str = "web"


@dataclass
class RunResult:
    ok: bool
    manifest: Optional[Manifest]
    plans: Dict[str, Any]
    error: Optional[GameForgeError] = None
    completed: List[str] = field(default_factory=list)
    artifacts: Dict[str, bytes] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "completed": list(self.completed),
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "error": self.error.to_dict() if self.error else None,
        }


class GameForgeConductor:
    STEPS = list(STEPS)

    def __init__(self, registry: Optional[EraRegistry] = None, config: Optional[ConductorConfig] = None,
                 hooks: Optional[Mapping[str, Callable[[str, Any], None]]] = None):
        self.registry = registry or EraRegistry()
        self.config = config or ConductorConfig()
        self.hooks = dict(hooks or {})
        self.reset()

    def reset(self) -> None:
        self.plans: Dict[str, Any] = {}
        self.log = ReceiptLog()
        self.binding: Optional[EraBinding] = None
        self.completed: List[str] = []
        self.artifacts: Dict[str, bytes] = {}

    # -- stepping -------------------------------------------------------
    @property
    def next_step(self) -> Optional[str]:
        return STEPS[len(self.completed)] if len(self.completed) < len(STEPS) else None

    def _check_order(self, step: str) -> None:
        if step not in STEPS:
            raise InputError(f"invalid step {step!r}", step=step)
        if step in self.completed:
            raise StepOrderError(f"step {step} already ran", step=step)
        if step != self.next_step:
            raise StepOrderError(f"step {step} requested but next is {self.next_step}", step=step)

    def _record(self, step: str, plan: Any, era_key: Optional[str]) -> str:
        assert self.binding is not None
        era = self.binding.bind(step, era_key)
        self.plans[step] = plan
        rec = self.log.append(step, era.key, plan)
        self.completed.append(step)
        hook = self.hooks.get(step)
        if hook:
            hook(step, plan)
        return rec.link

    def run_step(self, step: str, request: Union[VisionRequest, Mapping[str, Any], None] = None,
                 era_key: Optional[str] = None) -> str:
        self._check_order(step)
        cfg, p = self.config, self.plans
        if step == "vision":
            if request is None:
                raise InputError("vision step needs a request", step=step)
            req = request if isinstance(request, VisionRequest) else VisionRequest.from_mapping(request)
            era = self.registry.get(era_key or req.era)
            self.binding = EraBinding(era)
            plan: Any = S.vision(req)
            if plan.era != era.key:
                plan = type(plan)(**{**plan.__dict__, "era": era.key})
        else:
            assert self.binding is not None
            era = self.binding.era
            if step == "snowball":
                plan = S.snowball(p["vision"])
            elif step == "prototype":
                plan = S.prototype(p["vision"], p["snowball"])
            elif step == "mass_forge":
                plan = S.mass_forge(p["vision"], p["prototype"], era, cfg.budget_bytes)
                for a in plan.assets:
                    self.binding.require_asset(step, a.kind)
            elif step == "world":
                plan = S.world(p["vision"], era, cfg.regions)
            elif step == "cockpit":
                plan = S.cockpit(p["vision"], p["prototype"])
            else:  # export
                self.artifacts = S.render_artifacts(p["vision"], p["mass_forge"], p["world"], p["cockpit"])
                plan = S.export(p["vision"], self.artifacts, cfg.target)
        return self._record(step, plan, era_key)

    def manifest(self) -> Manifest:
        if tuple(self.completed) != STEPS:
            raise StepOrderError("manifest requested before export", detail={"completed": list(self.completed)})
        v = self.plans["vision"]
        meta = {"genre": v.genre, "target": self.config.target, "title": v.title,
                "budget_bytes": str(self.config.budget_bytes)}
        m = build_manifest(v.game_id, v.era, STEPS, self.artifacts, self.log, meta)
        for step in STEPS:
            if digest(self.plans[step]) != self.log.receipts[STEPS.index(step)].payload_digest:
                raise IntegrityError(f"plan for {step} mutated after receipt", step=step)
        return m

    def run(self, request: Union[VisionRequest, Mapping[str, Any]], era_key: Optional[str] = None) -> RunResult:
        """Run all seven steps; return a RunResult (never raises GameForgeError)."""
        self.reset()
        try:
            for step in STEPS:
                self.run_step(step, request if step == "vision" else None, era_key)
            m = self.manifest()
            return RunResult(True, m, dict(self.plans), None, list(self.completed), dict(self.artifacts))
        except GameForgeError as err:
            return RunResult(False, None, dict(self.plans), err, list(self.completed), {})

    # legacy-compatible convenience: list of receipt links
    def full_run(self, request: Union[VisionRequest, Mapping[str, Any]]) -> List[str]:
        res = self.run(request)
        if not res.ok:
            assert res.error is not None
            raise res.error
        return [r.link for r in self.log.receipts]
