"""GameForge context pipeline — one run, nine conserved-mass stages.

ingest → detect → tensor → lattice → oracle → forge → jeeves → emit → seal

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
    def __init__(self, *, bus: Optional[EventBus] = None, cockpit: Optional[Cockpit] = None) -> None:
        self.bus = bus or EventBus()
        self.cockpit = cockpit or Cockpit()
        self.composer = PipelineComposer(bus=self.bus)
        self.forge = Forge(bus=self.bus)
        self.jeeves = Jeeves(bus=self.bus)

    def execute(self, vision: str, *, era: Optional[str] = None,
                archetype: str = "extraction",
                target: str = "godot") -> Dict[str, Any]:
        cockpit = self.cockpit
        ctx: Dict[str, Any] = {
            "vision": vision or "",
            "era_hint": era,
            "archetype": archetype,
            "target": target,
            "cockpit": cockpit,
            "forge": self.forge,
            "jeeves": self.jeeves,
        }
        stages = [
            Stage("ingest", _stage_ingest),
            Stage("detect", _stage_detect),
            Stage("tensor", _stage_tensor),
            Stage("lattice", _stage_lattice),
            Stage("oracle", _stage_oracle),
            Stage("forge", _stage_forge),
            Stage("jeeves", _stage_jeeves),
            Stage("emit", _stage_emit),
            Stage("seal", _stage_seal),
        ]
        run = self.composer.execute("gameforge", stages, initial_context=ctx)
        payload = {
            "run": run.to_dict(),
            "succeeded": run.succeeded,
            "era": run.context.get("era"),
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
            "files": run.context.get("files") or {},
        }
        self.bus.emit("gameforge.run.finished", {
            "succeeded": run.succeeded,
            "era": payload["era"],
            "mass": payload["mass"],
        })
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
    if ctx.get("era_hint"):
        era, scores = ctx["era_hint"], {"hint": 1}
    else:
        era, scores = detect_era(ctx.get("vision") or "")
    _commit(ctx, "detect", ctx.get("vision") or "", era, {"era": era, "scores": scores})
    return {"era": era, "detect_scores": scores}


def _stage_tensor(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
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
    name = ctx.get("archetype") or "extraction"
    try:
        bp = default_library().build(forge, name)
    except Exception:
        bp = default_library().build(forge, "extraction")
    art = forge.materialise(bp, era=ctx["era"], target=ctx.get("target") or "godot")
    _commit(ctx, "forge", name, art.get("blueprint_id", ""), {
        "blueprint_id": art.get("blueprint_id"),
        "era": art.get("era"),
        "primary_dps": art.get("primary_dps"),
        "file_count": art.get("file_count"),
    })
    return {
        "blueprint_id": art.get("blueprint_id"),
        "primary_dps": art.get("primary_dps"),
        "artefact": art,
        "files": art.get("files") or {},
        "file_count": art.get("file_count") or len(art.get("files") or {}),
    }


def _stage_jeeves(ctx: Dict[str, Any]) -> Dict[str, Any]:
    jeeves: Jeeves = ctx["jeeves"]
    session = jeeves.open_session("pipeline", mode=SessionMode.TACTICAL)
    pack = jeeves.bind_era(ctx["era"])
    advice = jeeves.advise(session.session_id, {
        "heat": pack["heat"]["max_heat"] * pack["jeeves"]["heat_critical"],
        "has_weapon": False,
        "alive": True,
    })
    _commit(ctx, "jeeves", ctx["era"], advice["next"]["text"], advice["next"])
    return {"jeeves_advice": advice, "session_id": session.session_id}


def _stage_emit(ctx: Dict[str, Any]) -> Dict[str, Any]:
    files = ctx.get("files") or {}
    _commit(ctx, "emit", ctx["era"], f"{len(files)} files", {"file_count": len(files)})
    return {"emitted": True}


def _stage_seal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    cockpit: Cockpit = ctx["cockpit"]
    problems = cockpit.ledger.verify()
    _commit(ctx, "seal", "operator", "sealed" if not problems else "invalid",
            {"valid": not problems, "problems": problems, "mass": cockpit.snowball.mass})
    return {"sealed": not problems, "ledger_problems": problems}
