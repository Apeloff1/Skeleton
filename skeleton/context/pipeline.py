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
from skeleton.context.oracle import Magic8Ball
from skeleton.context.tensor import ContextTensor, detect_era
from skeleton.forge.archetypes import default_library
from skeleton.forge.universal import Forge
from skeleton.jeeves.core import Jeeves, SessionMode
from skeleton.kernel.events import EventBus
from skeleton.pipelines.composer import PipelineComposer, Stage

# Archetype names that ask the forge stage to compose the blueprint from the
# vision (skeleton.forge.vision_compose) instead of stamping a preset.
COMPOSE_ARCHETYPES = frozenset({"auto", "vision"})


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
                archetype: Optional[str] = None,
                target: str = "godot",
                project_root: Optional[str] = None,
                answers: Optional[Dict[str, str]] = None,
                overwrite: bool = False,
                blend: Optional[tuple] = None,
                generation: Optional[str] = None,
                playtest: Optional[str] = None,
                repair_mode: str = "apply",
                operator_tensor: Optional[ContextTensor] = None) -> Dict[str, Any]:
        """Run the ten-stage pipeline.

        ``playtest``: ``None``/"off" (default, static checks only), "auto"
        (boot the emitted build headless in Godot when a binary is available)
        or "require" (the emit stage fails unless the headless boot passes).
        ``repair_mode``: "apply" (default, revise until green) or "suggest"
        (verify loop proposes repairs without changing files).
        """
        from skeleton.forge.playtest import normalise_mode
        from skeleton.forge.repair import REPAIR_MODES
        playtest_mode = normalise_mode(playtest)
        if repair_mode not in REPAIR_MODES:
            raise ValueError(f"repair_mode must be one of {REPAIR_MODES}, got {repair_mode!r}")
        cockpit = self.cockpit
        taken = None
        if answers:
            from skeleton.context.questionnaire import intake
            taken = intake(answers)
            vision = vision or taken.vision
            era = era or taken.era
            # Keep the questionnaire's nuanced axis votes through the tensor
            # stage instead of resetting them to a generic era preset.
            cockpit.tensor = taken.tensor
        if generation is None:
            generation = getattr(cockpit, "generation", None)
        # Explicit argument > cockpit pin (BIND ARCHETYPE) > canonical preset.
        archetype = archetype or getattr(cockpit, "archetype", None) or "extraction"
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
            resolved_era = bound.get("era")
            if not era and resolved_era:
                era = str(resolved_era)
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
            "intake_tensor": (
                taken.tensor if taken is not None and era == taken.era and operator_tensor is None else None
            ),
            "operator_tensor": operator_tensor,
            "repair": True,
            "max_rounds": 3,
            "playtest_mode": playtest_mode,
            "repair_mode": repair_mode,
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
            "intake": taken.to_dict() if taken is not None else None,
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
                "verification": run.context.get("verification"),
                "verify_loop": run.context.get("verify_loop"),
                "repair": run.context.get("repair"),
                "composition": run.context.get("composition"),
            },
            "jeeves": run.context.get("jeeves_advice"),
            "cortex": run.context.get("cortex"),
            "G": ((run.context.get("cortex") or {}) or {}).get("G"),
            "law": ((run.context.get("cortex") or {}) or {}).get("law"),
            "files": run.context.get("files") or {},
            "sim": run.context.get("sim"),
            "project": run.context.get("project"),
            "build_report": run.context.get("build_report"),
            "playtest": run.context.get("playtest"),
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
        try:
            from skeleton.context.postprocess import postprocess_context
            payload = postprocess_context(run.context, payload)
        except Exception as exc:
            payload["postprocessed"] = False
            payload["postprocess_error"] = type(exc).__name__
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
    if not blend and not ctx.get("era_hint") and getattr(cockpit, "blend", None):
        blend = cockpit.blend
        ctx["blend"] = blend
    from skeleton.forge.hardware import detect_generation
    if not ctx.get("generation"):
        cockpit_generation = getattr(cockpit, "generation", None)
        if cockpit_generation:
            ctx["generation"] = cockpit_generation
            gscores = {"cockpit_hint": 1}
        else:
            try:
                gen, gscores = detect_generation(ctx.get("vision") or "")
            except ValueError:
                # Hardware generation is optional. Absence of generation
                # vocabulary must not abort the entire GameForge pipeline;
                # downstream era compilation owns its canonical default.
                gen, gscores = None, {}
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
    elif ctx.get("intake_tensor") is not None:
        cockpit.tensor = ctx["intake_tensor"]
    elif (ctx.get("operator_tensor") is not None
          and ctx["operator_tensor"].era == ctx["era"]):
        cockpit.tensor = ctx["operator_tensor"]
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
    composition = None
    if name in COMPOSE_ARCHETYPES:
        # Vision-derived component graph (opt-in via archetype="auto").
        from skeleton.forge.vision_compose import compose_from_vision
        bp, composed = compose_from_vision(forge, str(ctx.get("vision") or ""))
        composition = composed.to_dict()
        ctx["composition"] = composition
    else:
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
    repair = bool(ctx.get("repair", True))
    max_rounds = int(ctx.get("max_rounds", 3) or 3)
    art = forge.materialise(
        bp, era=ctx["era"], target=ctx.get("target") or "godot",
        pack=pack, build_plan=build_plan.to_dict(),
        repair=repair, max_rounds=max_rounds,
        repair_mode=str(ctx.get("repair_mode") or "apply"),
    )
    _commit(ctx, "forge", name, art.get("blueprint_id", ""), {
        "blueprint_id": art.get("blueprint_id"),
        "era": art.get("era"),
        "primary_dps": art.get("primary_dps"),
        "file_count": art.get("file_count"),
        "build_seed": build_plan.seed,
        "room_bias": build_plan.room_bias,
        "verification_accepted": (art.get("verification") or {}).get("accepted"),
        "verify_loop_rounds": ((art.get("verify_loop") or {}).get("trace") or {}).get("rounds"),
        "composition_features": (composition or {}).get("features"),
        "composition_fallback": (composition or {}).get("fallback"),
    })
    return {
        "blueprint_id": art.get("blueprint_id"),
        "primary_dps": art.get("primary_dps"),
        "artefact": art,
        "files": art.get("files") or {},
        "file_count": art.get("file_count") or len(art.get("files") or {}),
        "build_plan": build_plan.to_dict(),
        "verification": art.get("verification"),
        "verify_loop": art.get("verify_loop"),
        "repair": art.get("repair"),
        "composition": composition,
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
    # A required Godot boot failure must never publish an unverified tree.
    played = None
    mode = ctx.get("playtest_mode") or "off"
    if mode != "off":
        from skeleton.forge.playtest import playtest
        played = playtest(files)
        if mode == "require" and not played.get("passed"):
            detail = "; ".join(played.get("errors") or []) or played.get("reason") or played.get("status")
            raise RuntimeError(f"playtest {played.get('status')}: {detail}"[:600])
    project = None
    root = ctx.get("project_root")
    if root:
        from skeleton.forge.projector import write_project
        project = write_project(
            root, files, overwrite=bool(ctx.get("overwrite")),
            meta={"era": ctx.get("era"), "dps": ctx.get("primary_dps")},
        )
    _commit(ctx, "emit", ctx["era"], f"{len(files)} files", {
        "file_count": len(files),
        "root": None if not project else project["root"],
        "check": "ok",
        "playtest": None if played is None else played.get("status"),
    })
    return {"emitted": True, "project": project, "check_ok": True, "playtest": played}


def _publish_build_evidence(root, documents: Dict[str, str]) -> None:
    """Publish the final three receipt files without following output symlinks.

    All documents are serialized before writing; staging keeps partial
    serialization failures out of the project. Per-file os.replace does not
    traverse an existing link at the destination.
    """
    import os
    import shutil
    import tempfile
    from pathlib import Path

    root = Path(root)
    fixed = {"CONTEXT_LEDGER.json", "CONTEXT_TENSOR.json", "build_report.md"}
    if set(documents) != fixed:
        raise ValueError("unexpected final-evidence path set")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("final evidence project root must be a real directory")
    if any((root / name).is_symlink() for name in fixed):
        raise ValueError("final evidence destination is a symlink")
    stage = Path(tempfile.mkdtemp(prefix=".gameforge-evidence-", dir=root))
    try:
        for name, body in documents.items():
            if not isinstance(body, str):
                raise ValueError("evidence must be UTF-8 text")
            (stage / name).write_text(body, encoding="utf-8")
        for name in sorted(fixed):
            os.replace(stage / name, root / name)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _stage_seal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Seal the ledger and only then persist final build provenance.

    The emit stage cannot write a *final* ledger: the seal block and final mass
    do not exist yet. A corrupt ledger is an actual failed stage, never a
    successful response containing `sealed=False`.
    """
    cockpit: Cockpit = ctx["cockpit"]
    problems = cockpit.ledger.verify()
    if problems:
        raise RuntimeError("pre-seal ledger verification failed: " + "; ".join(problems[:8]))
    _commit(ctx, "seal", "operator", "sealed",
            {"valid": True, "problems": [], "mass_before_seal": cockpit.snowball.mass})
    problems = cockpit.ledger.verify()
    if problems:
        raise RuntimeError("post-seal ledger verification failed: " + "; ".join(problems[:8]))
    build_report = None
    project = ctx.get("project")
    if project:
        import hashlib
        import json
        from pathlib import Path

        root = Path(project["root"])
        ledger = cockpit.ledger.to_dict()
        tensor = cockpit.tensor.to_dict()
        # Serialize the final ledger and tensor, then publish all receipts
        # together after the report has been computed and validated.
        raw_plan = ctx.get("build_plan")
        plan = raw_plan.to_dict() if hasattr(raw_plan, "to_dict") else (raw_plan or {})
        if not isinstance(plan, dict):
            plan = {}
        seed = plan.get("seed")
        oracle = ctx.get("oracle_text")
        raw_field = ctx.get("field_pct")
        field = (f"{raw_field:.2f}%" if isinstance(raw_field, (int, float))
                 and not isinstance(raw_field, bool) and 0 <= raw_field <= 100
                 else "unmeasured (no verified field metric in this pipeline)")
        # Canonical source manifest digest: every emitted path and its content,
        # not just the file count. A real digest avoids fabricated evidence.
        files = ctx.get("files") or {}
        manifest = {
            name: hashlib.sha256(body.encode("utf-8")).hexdigest()
            for name, body in sorted(files.items())
        }
        manifest_sha = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        sim = ctx.get("sim") or {}
        playtest = ctx.get("playtest") or {}
        content = "\n".join([
            "# GameForge build report", "",
            f"- Era: {ctx.get('era') or 'not resolved'}",
            f"- Build seed: {seed if seed is not None else 'not recorded'}",
            f"- Rotor/oracle cue: {str(oracle or 'not recorded').replace(chr(10), ' ')[:160]}",
            f"- Conserved stage mass: {cockpit.snowball.mass:.6f}",
            f"- Field coverage: {field}",
            f"- Door graph simulation: {'passed' if sim.get('passed') else 'not passed'}",
            f"- Godot playtest: {playtest.get('status') or 'not requested'}",
            f"- Generated source files: {len(files)}",
            f"- Source manifest SHA-256: `{manifest_sha}`",
            f"- Ledger height: {cockpit.ledger.height}",
            f"- Ledger head SHA-256: `{cockpit.ledger.head.hash}`",
            "",
            "This report records pipeline results, not a manual gameplay QA signoff.",
            "An unmeasured metric does not establish its acceptance gate.",
            "",
        ])
        destination = root / "build_report.md"
        _publish_build_evidence(root, {
            "CONTEXT_LEDGER.json": json.dumps(ledger, indent=2, default=str),
            "CONTEXT_TENSOR.json": json.dumps(tensor, indent=2),
            "build_report.md": content,
        })
        build_report = {
            "path": str(destination),
            "manifest_sha256": manifest_sha,
            "ledger_head": cockpit.ledger.head.hash,
            "mass": cockpit.snowball.mass,
        }
    return {"sealed": True, "ledger_problems": [], "build_report": build_report}


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
