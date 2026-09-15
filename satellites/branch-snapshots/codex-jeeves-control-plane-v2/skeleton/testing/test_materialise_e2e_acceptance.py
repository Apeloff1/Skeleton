"""Materialise E2E acceptance — vision → forge materialise → verified artefact.

Proves the F-5 Godot spine works end-to-end from a vision-ish input without
importing GameForgeRun (Jeeves/cortex restore is #25) or requiring a Godot
binary / network. JSON/YAML structured_verify (#21) is not on main yet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from skeleton.context.tensor import ContextTensor, detect_era
from skeleton.forge.archetypes import default_library
from skeleton.forge.eras import compile_era
from skeleton.forge.universal import Forge
from skeleton.jeeves.builder import BuilderBrain
from skeleton.organism.quality_state import load_quality


def run_vision_to_verified_artefact(
    vision: str,
    *,
    root: Path,
    archetype: str = "extraction",
    target: str = "godot",
    repair: bool = True,
    max_rounds: int = 3,
    era_hint: Optional[str] = None,
) -> dict[str, Any]:
    """Thin glue: vision → era/pack/plan → materialise(+repair) → artefact.

    Mirrors ``pipeline._stage_forge`` without pulling GameForgeRun / Jeeves.
    """
    era, detect_scores = (era_hint, {"hint": 1}) if era_hint else detect_era(vision or "")
    forge = Forge(root=root)
    try:
        bp = default_library().build(forge, archetype)
    except Exception:
        bp = default_library().build(forge, "extraction")
    pack = compile_era(era)
    tensor = ContextTensor.from_era(era)
    build_plan = BuilderBrain().plan(
        pack, tensor=tensor, reading=None, cortex=None, last_walk=None,
    )
    art = forge.materialise(
        bp,
        era=era,
        target=target,
        pack=pack,
        build_plan=build_plan.to_dict(),
        repair=repair,
        max_rounds=max_rounds,
    )
    return {
        "vision": vision,
        "era": era,
        "detect_scores": detect_scores,
        "blueprint_id": art.get("blueprint_id"),
        "artefact": art,
        "files": art.get("files") or {},
        "file_count": art.get("file_count") or len(art.get("files") or {}),
        "verification": art.get("verification"),
        "verify_loop": art.get("verify_loop"),
        "repair": art.get("repair"),
        "build_plan": build_plan.to_dict(),
    }


def test_vision_to_godot_verified_artefact(tmp_path):
    """Acceptance: vision-ish input materialises a verified Godot artefact."""
    vision = "a cyberpunk extraction shooter with heat zones and loot rooms"
    out = run_vision_to_verified_artefact(vision, root=tmp_path, repair=True, max_rounds=3)

    assert out["era"] == "extraction_now"
    assert out["file_count"] > 0

    files: Mapping[str, str] = out["files"]
    assert "project.godot" in files
    assert "scenes/levels/run_level.tscn" in files
    assert any(path.endswith(".gd") for path in files)

    verification = out["verification"]
    assert verification is not None
    assert verification["accepted"] is True
    assert verification["score"] >= 0.7
    assert verification["reason"] == "accepted"

    # repair=True drives VerificationLoop on the Godot path
    loop = out["verify_loop"]
    assert loop is not None
    assert loop["accepted"] is True
    assert (loop.get("trace") or {}).get("rounds", 0) >= 1
    assert loop.get("code_verdict") is not None

    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["surface"] == "forge"
    assert rows[-1]["accepted"] is True


def test_vision_to_godot_artefact_writes_expected_spine_files(tmp_path):
    """Spot-check key emit artefacts exist after vision→materialise."""
    vision = "extraction run with event bus autoload and world map"
    out = run_vision_to_verified_artefact(vision, root=tmp_path, repair=True, max_rounds=2)
    files = out["files"]
    assert files["project.godot"].startswith("config_version=") or "config_version=" in files["project.godot"]
    assert 'run/main_scene=' in files["project.godot"] or "main_scene" in files["project.godot"]
    # Autoload / level spine commonly emitted by godot_emit
    assert any("event_bus" in p for p in files) or "EventBus" in files["project.godot"]
    assert out["verification"]["accepted"] is True
