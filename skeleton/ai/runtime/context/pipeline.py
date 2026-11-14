"""GameForge context pipeline — one run, ten conserved-mass stages.

ingest → detect → tensor → lattice → oracle → forge → jeeves → sim → emit → seal

Every stage pairs a Watson/Crick turn onto the helix and commits a
ledger block. Snowball mass hits 1.0 iff every stage succeeded. The
cockpit is an input, not a stage: operator commands may precede the
run and are already on the chain.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from skeleton.context.cockpit import Cockpit
from skeleton.context.galaxy_profile import (
    apply_galaxy_mechanics, attach_galaxy_profile, galaxy_profile_receipt, normalise_galaxy_profile,
)
from skeleton.context.dodeca import Dodecahedron
from skeleton.context.oracle import Magic8Ball
from skeleton.context.tensor import AXES, ContextTensor, detect_era
from skeleton.forge.archetypes import default_library
from skeleton.forge.universal import Forge
from skeleton.jeeves.core import Jeeves, SessionMode
from skeleton.kernel.events import EventBus
from skeleton.pipelines.composer import PipelineComposer, Stage

# Archetype names that ask the forge stage to compose the blueprint from the
# vision (skeleton.forge.vision_compose) instead of stamping a preset.
COMPOSE_ARCHETYPES = frozenset({"auto", "vision"})


def normalise_operator_axes(raw: Optional[Mapping[str, float]]) -> Dict[str, float]:
    """Fail closed on unknown, non-finite or out-of-range creator instruments.

    A sparse mapping overrides only explicitly touched design axes; no user,
    project or session state is stored by this validator.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > len(AXES):
        raise ValueError("operator_axes must be a mapping of at most ten design axes")
    for axis, value in raw.items():
        if not isinstance(axis, str) or axis not in AXES:
            raise ValueError("unknown operator axis")
        if type(value) not in (float, int) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("operator axis values must be finite numbers between 0 and 1")
    return {axis: float(raw[axis]) for axis in AXES if axis in raw}


def apply_operator_axes(tensor: ContextTensor, raw: Optional[Mapping[str, float]]) -> ContextTensor:
    """Apply sparse explicit creator edits *after* era/questionnaire resolution."""
    for axis, value in normalise_operator_axes(raw).items():
        tensor = tensor.with_axis(axis, value)
    return tensor


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
                operator_tensor: Optional[ContextTensor] = None,
                operator_axes: Optional[Mapping[str, float]] = None,
                galaxy_profile: Optional[Mapping[str, Any]] = None,
                playable_content: bool = False,
                playable_archetype: Optional[str] = None,
                playable_main_scene: bool = False,
                quest_content: bool = False,
                quest_length: int = 3) -> Dict[str, Any]:
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
        if playtest_mode != "off" and target != "godot":
            raise ValueError("native Godot playtest requires the Godot target")
        if type(playable_content) is not bool:
            raise ValueError("playable_content must be an explicit boolean opt-in")
        if playable_content and target != "godot":
            raise ValueError("playable archetype scenes require the Godot target")
        if type(playable_main_scene) is not bool:
            raise ValueError("playable_main_scene must be an explicit boolean")
        if not playable_content and (playable_archetype is not None or playable_main_scene):
            raise ValueError("playable selection requires playable_content opt-in")
        if playable_archetype is not None:
            from skeleton.forge.archetype_content import content_archetypes
            if type(playable_archetype) is not str or playable_archetype not in content_archetypes():
                raise ValueError("unsupported native playable archetype")
        if playable_main_scene and quest_content:
            raise ValueError("standalone playable mini-game startup conflicts with room-entry quest startup")
        if type(quest_content) is not bool:
            raise ValueError("quest_content must be an explicit boolean")
        if quest_content and target != "godot":
            raise ValueError("native quests require Godot target")
        if type(quest_length) is not int or not 1 <= quest_length <= 8:
            raise ValueError("quest_length must be an integer between 1 and 8")
        if repair_mode not in REPAIR_MODES:
            raise ValueError(f"repair_mode must be one of {REPAIR_MODES}, got {repair_mode!r}")
        axis_overrides = normalise_operator_axes(operator_axes)
        complete_galaxy_profile = normalise_galaxy_profile(galaxy_profile)
        galaxy_receipt = galaxy_profile_receipt(complete_galaxy_profile) if complete_galaxy_profile else None
        cockpit = self.cockpit
        # Freeze operator intent before stage execution. Implicit cockpit
        # blending applies only when neither an explicit era nor questionnaire
        # choices supersede it. Otherwise the declared input wins.
        inherited_blend = (
            tuple(cockpit.blend)
            if blend is None and era is None and not answers and cockpit.blend
            else None
        )
        effective_blend = blend if blend is not None else inherited_blend
        if inherited_blend is not None and operator_tensor is None:
            # A manual SET AXIS after BLEND must survive forge execution,
            # including an operator ROLL ORACLE before the build.
            operator_tensor = cockpit.tensor
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
            # A pinned cockpit or explicit blend outranks automatic reference inference.
            if not era and not effective_blend and resolved_era:
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
            "blend": effective_blend,
            "blend_source": (
                "argument" if blend is not None else
                "cockpit" if inherited_blend is not None else "none"
            ),
            "generation": generation,
            "reference": hit,
            "intake_tensor": (
                taken.tensor if taken is not None and era == taken.era and operator_tensor is None else None
            ),
            "operator_tensor": operator_tensor,
            "operator_axes": axis_overrides,
            "galaxy_profile": complete_galaxy_profile,
            "galaxy_receipt": galaxy_receipt,
            "repair": True,
            "max_rounds": 3,
            "playtest_mode": playtest_mode,
            "repair_mode": repair_mode,
            "playable_content": playable_content,
            "playable_archetype_selection": playable_archetype,
            "playable_main_scene": playable_main_scene,
            "quest_content": quest_content,
            "quest_length": quest_length,
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
        from skeleton.forge.source_manifest import source_manifest
        generated = run.context.get("files") or {}
        # A failed pipeline may have partial output. Never present its digest
        # as a sealed, verified source manifest.
        emitted_manifest = source_manifest(generated) if run.succeeded and generated else None
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
                "playable_archetype": run.context.get("playable_archetype"),
                "playable_scene": run.context.get("playable_scene"),
                "playable_launch_scene": run.context.get("playable_launch_scene"),
                "playable_launcher": run.context.get("playable_launcher"),
            },
            "jeeves": run.context.get("jeeves_advice"),
            "cortex": run.context.get("cortex"),
            "G": ((run.context.get("cortex") or {}) or {}).get("G"),
            "law": ((run.context.get("cortex") or {}) or {}).get("law"),
            "files": run.context.get("files") or {},
            "source_manifest": emitted_manifest,
            "sim": run.context.get("sim"),
            "project": run.context.get("project"),
            "build_report": run.context.get("build_report"),
            "playtest": run.context.get("playtest"),
            "cortex_observe": run.context.get("cortex_observe"),
            "build_plan": (run.context.get("build_plan").to_dict()
                           if hasattr(run.context.get("build_plan"), "to_dict")
                           else run.context.get("build_plan")),
        }
        if axis_overrides:
            payload["operator_axes"] = axis_overrides
        if galaxy_receipt:
            payload["galaxy_profile"] = {
                **galaxy_receipt,
                "emitted": bool(
                    run.succeeded and
                    "design/galaxy_studio_profile.json" in (run.context.get("files") or {})
                ),
            }
            if run.context.get("galaxy_mechanics") is not None:
                payload["galaxy_mechanics"] = run.context["galaxy_mechanics"]
        if playable_content and run.context.get("playable_scene_playtest") is not None:
            payload["playable_scene_playtest"] = run.context["playable_scene_playtest"]
        if playable_content and run.context.get("playable_receipt") is not None:
            payload["playable_prototype"] = {
                **run.context["playable_receipt"],
                "sealed": bool(run.succeeded and emitted_manifest is not None),
            }
        if quest_content and run.context.get("native_quest_receipt") is not None:
            payload["native_quest"] = {
                **run.context["native_quest_receipt"],
                "sealed": bool(run.succeeded and emitted_manifest is not None),
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
    details = {"chars": len(vision)}
    if ctx.get("galaxy_receipt"):
        details["galaxy_profile_sha256"] = ctx["galaxy_receipt"]["sha256"]
    _commit(ctx, "ingest", vision, "ingested", details)
    return {"ingested": True, "chars": len(vision)}


def _stage_detect(ctx: Dict[str, Any]) -> Dict[str, Any]:
    blend = ctx.get("blend")
    cockpit: Cockpit = ctx["cockpit"]
    # All operator/CLI precedence is resolved at execute() entry. Do not
    # silently resurrect mutable cockpit blending inside an individual stage.
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
    operator = ctx.get("operator_tensor")
    if operator is not None and operator.era == ctx["era"]:
        # An explicitly selected era also uses this branch when the saved
        # tensor refers to that era; otherwise it is never resurrected.
        cockpit.tensor = operator
    elif blend and len(blend) >= 2:
        t = float(blend[2]) if len(blend) > 2 else 0.5
        cockpit.tensor = ContextTensor.from_era(str(blend[0])).lerp(
            ContextTensor.from_era(str(blend[1])), t
        )
        object.__setattr__(cockpit.tensor, "era", ctx["era"])
    elif ctx.get("intake_tensor") is not None:
        cockpit.tensor = ctx["intake_tensor"]
    else:
        cockpit.tensor = ContextTensor.from_era(ctx["era"])
    cockpit.tensor = apply_operator_axes(cockpit.tensor, ctx.get("operator_axes"))
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
    build_plan, galaxy_mechanics = apply_galaxy_mechanics(
        build_plan, ctx.get("galaxy_profile"),
    )
    if galaxy_mechanics is not None:
        ctx["galaxy_mechanics"] = galaxy_mechanics
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
    from skeleton.forge.source_manifest import source_manifest

    files = ctx.get("files") or {}
    if ctx.get("playable_content"):
        from skeleton.forge.archetype_content import content_archetypes, attach_archetype_content
        requested = ctx.get("playable_archetype_selection") or ctx.get("archetype") or "extraction"
        selected = requested if requested in content_archetypes() else "extraction"
        files = attach_archetype_content(
            files, selected, tuning=ctx.get("operator_axes") or None,
        )
        ctx["files"] = files
        ctx["file_count"] = len(files)
        ctx["playable_archetype"] = selected
        playable_scene = f"res://scenes/archetypes/{selected}/main.tscn"
        ctx["playable_scene"] = playable_scene
        if ctx.get("playable_main_scene"):
            existing = 'run/main_scene="res://scenes/levels/run_level.tscn"'
            if files.get("project.godot", "").count(existing) != 1:
                raise ValueError("canonical startup scene contract changed")
            files["project.godot"] = files["project.godot"].replace(
                existing, f'run/main_scene="{playable_scene}"',
            )
            ctx["playable_launch_scene"] = playable_scene
        else:
            # A source-only extra scene is unusable for normal players.
            # Install a real in-game toggle without changing the main world.
            from skeleton.forge.archetype_content import (
                attach_playable_launcher, PLAYABLE_LAUNCHER_PATH,
            )
            files = attach_playable_launcher(files, selected)
            ctx["files"] = files
            ctx["file_count"] = len(files)
            ctx["playable_launcher"] = PLAYABLE_LAUNCHER_PATH
    if ctx.get("galaxy_profile") is not None:
        files = attach_galaxy_profile(files, ctx["galaxy_profile"])
        ctx["files"] = files
        ctx["file_count"] = len(files)
    if ctx.get("quest_content"):
        from skeleton.ai.game_builder.godot_quest_bridge import attach_native_quest
        files, receipt = attach_native_quest(files, length=ctx.get("quest_length", 3))
        ctx["files"] = files
        ctx["file_count"] = len(files)
        ctx["native_quest_receipt"] = receipt
    # Validate names in both API/in-memory and disk build modes, before any
    # expensive engine checks or project publication.
    validated_manifest = source_manifest(files)
    if ctx.get("playable_content"):
        import hashlib
        import json
        selected = ctx["playable_archetype"]
        paths = [
            f"scenes/archetypes/{selected}/main.tscn",
            f"scripts/archetypes/{selected}/player_controller.gd",
            f"scripts/archetypes/{selected}/core_loop.gd",
        ]
        if ctx.get("playable_launcher"):
            paths.append(ctx["playable_launcher"])
        from skeleton.forge.playable_tuning import SOURCE_PATH as TUNING_PATH
        if TUNING_PATH in files:
            paths.append(TUNING_PATH)
            ctx["playable_tuning"] = json.loads(files[TUNING_PATH])
        source_hashes = {
            path: validated_manifest["files"][path] for path in sorted(paths)
        }
        source_digest = hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        ctx["playable_receipt"] = {
            "schema": "skeleton.gameforge.playable_source.v1",
            "mode": selected,
            "scene": ctx["playable_scene"],
            "launch_scene": ctx.get("playable_launch_scene"),
            "launcher": ctx.get("playable_launcher"),
            "source_files": source_hashes,
            "source_sha256": source_digest,
            **({"tuning": ctx["playable_tuning"]} if ctx.get("playable_tuning") else {}),
        }
        from skeleton.forge.playable_provenance import verify_playable_source
        if not verify_playable_source(files, ctx["playable_receipt"]):
            raise ValueError("playable prototype differs from deterministic authored source")
    ok, problems = check_ok(files)
    if not ok:
        raise RuntimeError("gdscript check failed: " + "; ".join(problems[:8]))
    # A required Godot boot failure must never publish an unverified tree.
    played = None
    mode = ctx.get("playtest_mode") or "off"
    if mode != "off":
        from skeleton.forge.playtest import playtest
        played = playtest(files)
        if mode == "require" and not (played.get("status") == "passed" and played.get("passed") is True):
            detail = "; ".join(played.get("errors") or []) or played.get("reason") or played.get("status")
            raise RuntimeError(f"playtest {played.get('status')}: {detail}"[:600])
    # Boot the selected sidecar itself before materialising the final project.
    # Default-world success does not prove that any of the eight playable
    # prototypes completes its own authored objective.
    scene_played = None
    if ctx.get("playable_content") and mode != "off":
        from skeleton.forge.playtest import playtest_archetype_scene
        scene_played = playtest_archetype_scene(
            files, str(ctx.get("playable_archetype") or ""),
        )
        ctx["playable_scene_playtest"] = scene_played
        if mode == "require" and not (
            scene_played.get("status") == "passed"
            and scene_played.get("passed") is True
        ):
            detail = "; ".join(scene_played.get("errors") or []) or scene_played.get("reason") or scene_played.get("status")
            raise RuntimeError(f"playable scene {scene_played.get('status')}: {detail}"[:600])
    project = None
    root = ctx.get("project_root")
    if root:
        from skeleton.forge.projector import write_project
        project = write_project(
            root, files, overwrite=bool(ctx.get("overwrite")),
            meta={"era": ctx.get("era"), "dps": ctx.get("primary_dps")},
        )
    details = {
        "file_count": len(files),
        "root": None if not project else project["root"],
        "check": "ok",
        "playtest": None if played is None else played.get("status"),
        "playable_scene_playtest": None if scene_played is None else scene_played.get("status"),
    }
    if ctx.get("galaxy_receipt"):
        details["galaxy_profile_sha256"] = ctx["galaxy_receipt"]["sha256"]
    if ctx.get("native_quest_receipt"):
        details["native_quest_sha256"] = ctx["native_quest_receipt"]["quest_sha256"]
    _commit(ctx, "emit", ctx["era"], f"{len(files)} files", details)
    return {"emitted": True, "project": project, "check_ok": True, "playtest": played, "playable_scene_playtest": scene_played}


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
        import json
        from pathlib import Path
        from skeleton.forge.source_manifest import source_manifest

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
        # Exactly the same source digest as CLI, API and FORGE_MANIFEST.
        files = ctx.get("files") or {}
        manifest_sha = source_manifest(files)["sha256"]
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
