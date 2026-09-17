"""7-step GameForge conductor cards. Batch-complete is not SOTA."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.catalog import catalog
from skeleton.game.critique import improve
from skeleton.game.era_bind import HOUSE_ERA, bind_era
from skeleton.game.extract_loop import run_loop
from skeleton.game.intent import compile_intent
from skeleton.game.mass import observe_mass, trajectory
from skeleton.game.pack import validate_pack
from skeleton.game.replay import record, verify
from skeleton.game.rights import rights_card
from skeleton.game.session import run_session
from skeleton.game.world_graph import place, walk


STEPS = (
    "vision",
    "snowball",
    "prototype",
    "mass_forge",
    "world",
    "cockpit",
    "export",
)


class ConductorError(ValueError):
    """Conductor contract violation."""


def _step_card(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if name not in STEPS:
        raise ConductorError(f"unknown step: {name}")
    return {
        "kind": "gf-step",
        "step": name,
        "exit": dict(payload),
        "stored_prose": 0,
    }


def execute(
    *,
    seed: int = 8847291,
    vision: str = "NEXUS-EXTRACT #807",
    era: str = HOUSE_ERA,
    forges: int = 4,
) -> dict[str, Any]:
    if forges < 1 or forges > 20:
        raise ConductorError("forges out of range")
    reference = bind_era(era=era, title="NEXUS-EXTRACT", citation="#807")
    intent = compile_intent(vision)
    vision_card = _step_card(
        "vision",
        {"intent": intent, "conflicts": intent["conflicts"], "reference": reference},
    )
    mass_path = trajectory(1.0, forges)
    snowball = _step_card(
        "snowball",
        {
            "current_mass": mass_path[-1],
            "target_mass": mass_path[-1],
            "iteration_count": forges,
            "seed": int(seed),
            "mass": observe_mass(g=mass_path[-1], g0=mass_path[0], citation="#807"),
        },
    )
    trace = record(
        seed=seed,
        inputs=[{"t": 0, "verb": "attack"}, {"t": 1, "verb": "defend"}, {"t": 2, "verb": "wait"}],
    )
    check = verify(trace.to_dict())
    proto = _step_card(
        "prototype",
        {"digest": check["digest"], "frames": check["frames"], "runnable": True},
    )
    recipes = catalog(
        [
            {"id": "scrap-kit", "inputs": {"scrap": 2}, "outputs": {"parts": 1}},
            {"id": "heat-sink", "inputs": {"parts": 1}, "outputs": {"coolant": 1}},
        ]
    )
    pack = validate_pack(
        {
            "combat": {"style": "turn_based", "include_magic": True},
            "economy": {"currencies": ["scrap", "parts"]},
            "progression": {"style": "linear", "max_level": 20},
            "ai": {
                "entity_type": "stalker",
                "behaviors": ["patrol", "chase"],
                "aggression_level": 0.6,
                "intelligence_level": 0.4,
            },
        }
    )
    rights = rights_card(
        asset_id="nexus-pack",
        source="repo:Apeloff1/Skeleton",
        license_id="internal",
    )
    mass_forge = _step_card(
        "mass_forge",
        {"catalog": recipes, "pack": pack, "rights": rights, "manifests_first": True},
    )
    graph = place(seed=int(seed), rooms=5)
    walked = walk(graph)
    world = _step_card(
        "world",
        {"graph": graph, "walk": walked, "domains": graph["domains"]},
    )
    taste = improve(
        {"fun": 0.62, "clarity": 0.71, "feasibility": 0.58, "originality": 0.66},
        seed=int(seed),
    )
    cockpit = _step_card("cockpit", {"improve": taste, "retune": False})
    loop = run_loop()
    session = run_session(seed=seed, inputs=[{"t": 0, "verb": "attack"}], forges=forges)
    export = _step_card(
        "export",
        {
            "session_digest": session["digest"],
            "replay_digest": session["replay_digest"],
            "extract_loop": loop["final"],
            "files": ["data/spec.json", "reports/build_report.md"],
        },
    )
    cards = [vision_card, snowball, proto, mass_forge, world, cockpit, export]
    empty = [card["step"] for card in cards if not card["exit"]]
    if empty:
        raise ConductorError(f"empty exit: {empty[0]}")
    return {
        "kind": "gf-run",
        "seed": int(seed),
        "reference": reference,
        "steps": cards,
        "mass_trajectory": mass_path,
        "weakest": taste["doctor"],
        "sota_ready": False,
        "law": "batch_complete_is_not_sota",
        "stored_prose": 0,
        "ok": True,
    }
