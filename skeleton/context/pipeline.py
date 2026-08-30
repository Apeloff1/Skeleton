"""GameForge context pipeline — one run, ten conserved-mass stages.

ingest → detect → tensor → lattice → oracle → forge → jeeves → sim → emit → seal

Every stage pairs a Watson/Crick turn onto the helix and commits a
ledger block. Snowball mass hits 1.0 iff every stage succeeded. The
cockpit is an input, not a stage: operator commands may precede the
run and are already on the chain.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.context.cockpit import Cockpit
from skeleton.context.dodeca import Dodecahedron
from skeleton.context.helix import DNAHelix
from skeleton.context.ledger import ContextLedger
from skeleton.context.oracle import Magic8Ball
from skeleton.context.snowball import Snowball
from skeleton.context.tensor import ContextTensor, detect_era
from skeleton.forge.archetypes import default_library
from skeleton.forge.universal import Forge
from skeleton.jeeves.core import Jeeves, SessionMode
from skeleton.kernel.events import EventBus
from skeleton.pipelines.composer import PipelineComposer, Stage


class GameForgeRun:
    def __init__(self, *, bus: Optional[EventBus] = None, cockpit: Optional[Cockpit] = None,
                 jeeves: Optional[Jeeves] = None, live: bool = False) -> None:
        self.bus = bus or EventBus()
        self.cockpit = cockpit or Cockpit()
        self.composer = PipelineComposer(bus=self.bus)
        self.forge = Forge(bus=self.bus)
        if live:
            from skeleton.cortex.live import live_jeeves
            self.jeeves = live_jeeves()
            self._persist = True
        else:
            self.jeeves = jeeves or Jeeves(bus=self.bus)
            self._persist = False

    @classmethod
    def live(cls, *, cockpit: Optional[Cockpit] = None) -> "GameForgeRun":
        return cls(cockpit=cockpit, live=True)

    def execute(self, vision: str, *, era: Optional[str] = None,
                archetype: str = "extraction",
                target: str = "godot",
                project_root: Optional[str] = None,
                answers: Optional[Dict[str, str]] = None,
                overwrite: bool = False,
                blend: Optional[tuple] = None,
                generation: Optional[str] = None) -> Dict[str, Any]:
        cockpit = self.cockpit
        if answers:
            from skeleton.context.questionnaire import intake
            taken = intake(answers)
            vision = vision or taken.vision
            era = era or taken.era
            cockpit.tensor = taken.tensor
        if generation is None:
            generation = getattr(cockpit, "generation", None)
        try:
            from skeleton.cortex.era_bind import resolve
            bound = resolve(vision or era or "")
            hit = {
                "title": bound.get("title"),
                "era": bound.get("era"),
                "citation": bound.get("citation"),
                "url": bound.get("url"),
                "dialect": bound.get("dialect"),
            } if bound.get("hit") else None
            era = era or str(bound.get("era") or era)
            extra = str(bound.get("dialect") or "")
            if extra and extra not in (vision or ""):
                vision = f"{vision} {extra}".strip()
        except Exception:
            hit = None
        ctx: Dict[str, Any] = {
            "vision": vision or "",
            "era_hint": era,
            "archetype": archetype,
            "target": target,
            "project_root": project_root,
            "overwrite": overwrite,
            "cockpit": cockpit,
            "forge": self.forge,
            "jeeves": self.jeeves,
            "blend": blend,
            "generation": generation,
            "reference": hit,
        }
        stages = [
            Stage("ingest", _stage_ingest),
            Stage("detect", _stage_detect),
            Stage("tensor", _stage_tensor),
            Stage("lattice", _stage_lattice),
            Stage("oracle", _stage_oracle),
            Stage("forge", _stage_forge),
            Stage("jeeves", _stage_jeeves),
            Stage("sim", _stage_sim),
            Stage("emit", _stage_emit),
            Stage("seal", _stage_seal),
        ]
        run = self.composer.execute("gameforge", stages, initial_context=ctx)
        payload = {
            "run": run.to_dict(),
            "succeeded": run.succeeded,
            "era": run.context.get("era"),
            "generation": run.context.get("generation"),
            "reference": (run.context.get("reference") or {}).get("title") if isinstance(run.context.get("reference"), dict) else None,
            "citation": (run.context.get("reference") or {}).get("citation") if isinstance(run.context.get("reference"), dict) else None,
            "stored_prose": 0,
            "mass": cockpit.snowball.mass,
            "complete": cockpit.snowball.complete,
            "tensor": cockpit.tensor.to_dict(),
            "lattice": cockpit.lattice.to_dict(),
            "oracle": cockpit.last_oracle.to_dict() if cockpit.last_oracle else None,
            "helix": cockpit.helix.to_dict(),
            "ledger": {
                "height": cockpit.ledger.height,
                "head": cockpit.ledger.head.hash,
                "valid": not cockpit.ledger.verify(),
            },
            "snowball": cockpit.snowball.to_dict(),
            "forge": {
                "blueprint_id": run.context.get("blueprint_id"),
                "file_count": run.context.get("file_count"),
                "primary_dps": run.context.get("primary_dps"),
            },
            "jeeves": run.context.get("jeeves_advice"),
            "cortex": run.context.get("cortex"),
            "G": ((run.context.get("cortex") or {}) or {}).get("G"),
            "law": ((run.context.get("cortex") or {}) or {}).get("law"),
            "files": run.context.get("files") or {},
            "sim": run.context.get("sim"),
            "project": run.context.get("project"),
            "cortex_observe": run.context.get("cortex_observe"),
            "build_plan": (run.context.get("build_plan").to_dict()
                           if hasattr(run.context.get("build_plan"), "to_dict")
                           else run.context.get("build_plan")),
        }
        self.bus.emit("gameforge.run.finished", {
            "succeeded": run.succeeded,
            "era": payload["era"],
            "mass": payload["mass"],
        })
        if self._persist:
            from skeleton.cortex.live import persist
            saved = persist()
            payload["own"] = saved
        return payload


def _commit(ctx: Dict[str, Any], stage: str, operator: str, system: str, extra: Dict[str, Any]) -> None:
    cockpit: Cockpit = ctx["cockpit"]
    bp = cockpit.helix.pair(stage, operator, system)
    mass = cockpit.snowball.mark(stage)
    cockpit.ledger.append(
        stage, extra,
        mass=mass, tensor_fp=cockpit.tensor.fingerprint(),
        leaves=[stage, bp.watson, bp.crick, operator[:80], system[:80]],
    )


def _stage_ingest(ctx: Dict[str, Any]) -> Dict[str, Any]:
    vision = ctx.get("vision") or ""
    _commit(ctx, "ingest", vision, "ingested", {"chars": len(vision)})
    return {"ingested": True, "chars": len(vision)}


def _stage_detect(ctx: Dict[str, Any]) -> Dict[str, Any]:
    blend = ctx.get("blend")
    cockpit: Cockpit = ctx["cockpit"]
    if not blend and getattr(cockpit, "blend", None):
        blend = cockpit.blend
        ctx["blend"] = blend
    from skeleton.forge.hardware import detect_generation, attach
    if not ctx.get("generation"):
        gen, gscores = detect_generation(ctx.get("vision") or "")
        if getattr(cockpit, "generation", None):
            gen = cockpit.generation
        ctx["generation"] = gen
    else:
        gscores = {"hint": 1}
    if blend and len(blend) >= 2:
        from skeleton.forge.eras import blend_eras
        t = float(blend[2]) if len(blend) > 2 else 0.5
        pack = blend_eras(str(blend[0]), str(blend[1]), t, generation=ctx.get("generation"))
        era, scores = pack["era"], {"blend": 1}
        ctx["pack"] = pack
    elif ctx.get("era_hint"):
        era, scores = ctx["era_hint"], {"hint": 1}
    else:
        era, scores = detect_era(ctx.get("vision") or "")
    _commit(ctx, "detect", ctx.get("vision") or "", era, {
        "era": era, "scores": scores, "generation": ctx.get("generation"), "gen_scores": gscores,
    })
    return {"era": era, "detect_scores": scores, "generation": ctx.get("generation")}


def _stage_tensor(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
    blend = ctx.get("blend")
    if blend and len(blend) >= 2:
        t = float(blend[2]) if len(blend) > 2 else 0.5
        cockpit.tensor = ContextTensor.from_era(str(blend[0])).lerp(
            ContextTensor.from_era(str(blend[1])), t
        )
        # keep the blended era label on the cube
        object.__setattr__(cockpit.tensor, "era", ctx["era"])
    else:
        cockpit.tensor = ContextTensor.from_era(ctx["era"])
    _commit(ctx, "tensor", ctx["era"], cockpit.tensor.fingerprint(), cockpit.tensor.as_dict())
    return {"tensor_fp": cockpit.tensor.fingerprint()}


def _stage_lattice(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
    lattice = Dodecahedron.from_tensor(cockpit.tensor)
    hottest = lattice.hottest(1)[0][0]
    _commit(ctx, "lattice", ctx["era"], hottest, lattice.to_dict())
    return {"hottest_face": hottest}


def _stage_oracle(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
    reading = Magic8Ball(cockpit.lattice).roll(cockpit.tensor)
    cockpit.last_oracle = reading
    _commit(ctx, "oracle", ctx["era"], reading.text, reading.to_dict())
    return {"oracle_text": reading.text, "oracle_index": reading.index}


def _stage_forge(ctx: Dict[str, Any]) -> Dict[str, Any]:
    forge: Forge = ctx["forge"]
    cockpit: Cockpit = ctx["cockpit"]
    name = ctx.get("archetype") or "extraction"
    try:
        bp = default_library().build(forge, name)
    except Exception:
        bp = default_library().build(forge, "extraction")
    pack = ctx.get("pack")
    if not pack:
        from skeleton.forge.eras import compile_era
        pack = compile_era(ctx["era"], generation=ctx.get("generation"))
        ctx["pack"] = pack
    else:
        from skeleton.forge.hardware import attach
        if "hardware" not in pack:
            pack = attach(pack, ctx.get("generation"))
            ctx["pack"] = pack
    from skeleton.jeeves.builder import BuilderBrain
    jeeves = ctx.get("jeeves")
    last_walk = getattr(jeeves, "last_walk", None) if jeeves is not None else None
    cortex = jeeves.cortex if jeeves is not None else None
    build_plan = BuilderBrain().plan(
        pack, tensor=cockpit.tensor, reading=cockpit.last_oracle,
        cortex=cortex, last_walk=last_walk,
    )
    ctx["build_plan"] = build_plan
    art = forge.materialise(
        bp, era=ctx["era"], target=ctx.get("target") or "godot",
        pack=pack, build_plan=build_plan.to_dict(),
    )
    _commit(ctx, "forge", name, art.get("blueprint_id", ""), {
        "blueprint_id": art.get("blueprint_id"),
        "era": art.get("era"),
        "primary_dps": art.get("primary_dps"),
        "file_count": art.get("file_count"),
        "build_seed": build_plan.seed,
        "room_bias": build_plan.room_bias,
    })
    return {
        "blueprint_id": art.get("blueprint_id"),
        "primary_dps": art.get("primary_dps"),
        "artefact": art,
        "files": art.get("files") or {},
        "file_count": art.get("file_count") or len(art.get("files") or {}),
        "build_plan": build_plan.to_dict(),
    }


def _stage_jeeves(ctx: Dict[str, Any]) -> Dict[str, Any]:
    jeeves: Jeeves = ctx["jeeves"]
    session = jeeves.open_session("pipeline", mode=SessionMode.TACTICAL)
    pack = ctx.get("pack") or ctx.get("artefact", {}).get("pack")
    pack = jeeves.bind_pack(pack) if pack else jeeves.bind_era(ctx["era"])
    raw = ctx.get("build_plan")
    if raw is not None and hasattr(raw, "to_dict"):
        plan = raw.to_dict()
        jeeves.last_plan = raw
    else:
        plan = dict(raw or {})
    spawn_weapon = bool(plan.get("spawn_weapon"))
    advice = jeeves.advise(session.session_id, {
        "heat": pack["heat"]["max_heat"] * pack["jeeves"]["heat_critical"],
        "has_weapon": spawn_weapon,
        "alive": True,
    })
    if plan:
        advice = dict(advice)
        advice["briefing"] = plan.get("briefing")
        advice["build_plan"] = plan
    cockpit: Cockpit = ctx["cockpit"]
    trace = jeeves.think(ctx.get("vision") or ctx.get("era") or "", context={
        "era": ctx.get("era"),
        "tensor": cockpit.tensor.as_dict(),
        "pack_dps": pack.get("primary_dps"),
        "pack_ttk": pack.get("ttk"),
        "hottest": cockpit.lattice.hottest(1)[0][0],
        "reference": ctx.get("reference"),
    })
    _commit(ctx, "jeeves", ctx["era"], advice["next"]["text"], advice["next"])
    return {
        "jeeves_advice": advice,
        "session_id": session.session_id,
        "cortex": trace.to_dict(),
    }


def _stage_emit(ctx: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.forge.gdscript_check import check_ok
    files = ctx.get("files") or {}
    ok, problems = check_ok(files)
    if not ok:
        raise RuntimeError("gdscript check failed: " + "; ".join(problems[:8]))
    project = None
    root = ctx.get("project_root")
    if root:
        from skeleton.forge.projector import write_project
        import json
        from pathlib import Path
        project = write_project(
            root, files, overwrite=bool(ctx.get("overwrite")),
            meta={"era": ctx.get("era"), "dps": ctx.get("primary_dps")},
        )
        cockpit = ctx["cockpit"]
        Path(root, "CONTEXT_LEDGER.json").write_text(
            json.dumps(cockpit.ledger.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        Path(root, "CONTEXT_TENSOR.json").write_text(
            json.dumps(cockpit.tensor.to_dict(), indent=2), encoding="utf-8"
        )
    _commit(ctx, "emit", ctx["era"], f"{len(files)} files", {
        "file_count": len(files),
        "root": None if not project else project["root"],
        "check": "ok",
    })
    return {"emitted": True, "project": project, "check_ok": True}


def _stage_seal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
    problems = cockpit.ledger.verify()
    _commit(ctx, "seal", "operator", "sealed" if not problems else "invalid",
            {"valid": not problems, "problems": problems, "mass": cockpit.snowball.mass})
    return {"sealed": not problems, "ledger_problems": problems}


def _stage_sim(ctx: Dict[str, Any]) -> Dict[str, Any]:
    from skeleton.forge.sim import simulate_session
    import json
    art = ctx.get("artefact") or {}
    pack = art.get("pack") or ctx.get("pack") or {}
    files = ctx.get("files") or art.get("files") or {}
    graph = None
    raw = files.get("data/rooms.json")
    if raw:
        graph = json.loads(raw)
    plan = ctx.get("build_plan")
    plan_d = plan.to_dict() if hasattr(plan, "to_dict") else (plan or None)
    report = simulate_session(pack, graph=graph, plan=plan_d)
    jeeves = ctx.get("jeeves")
    if jeeves is not None and hasattr(jeeves, "observe_run"):
        ctx["cortex_observe"] = jeeves.observe_run(
            era=str(ctx.get("era") or pack.get("era") or ""),
            walk=report.walk or {},
            plan=plan_d or {},
            vision=str(ctx.get("vision") or ""),
        )
    _commit(ctx, "sim", ctx.get("era") or "", "pass" if report.passed else "fail", report.to_dict())
    if not report.passed:
        raise RuntimeError("session sim failed: " + "; ".join(report.notes))
    return {"sim": report.to_dict()}
