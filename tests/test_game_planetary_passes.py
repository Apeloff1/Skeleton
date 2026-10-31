"""Planetary follow-up specs keep a billion maps per family and 900,000 cognition steps."""
from __future__ import annotations

import tempfile
from pathlib import Path

from skeleton.ai.runtime.inference.game_map_variants import BILLION_MAPS, FOLLOWUP_FAMILIES
from skeleton.ai.runtime.inference.game_planetary_passes import (
    COGNITION_STEPS,
    PLANETARY_TRAINING_PASS_SPECS,
    assess_cognition,
    render_cognition,
    run_planetary_training_passes,
    validate_cognition,
)


def test_followup_specs_are_one_billion_per_family_and_900k_cognition_steps():
    by_id = {spec["pass_id"]: spec for spec in PLANETARY_TRAINING_PASS_SPECS}
    assert by_id["map-billion"]["run"] is False
    follow = by_id["tabletop-followup"]
    assert follow["run"] is True
    assert follow["budget_per_family"] == BILLION_MAPS == 1_000_000_000
    assert follow["families"] == FOLLOWUP_FAMILIES
    cognition = by_id["jeeves-cognition"]
    assert cognition["budget"] == COGNITION_STEPS == 900_000
    assert cognition["unit"] == "steps"
    report = validate_cognition()
    assert report["checked"] == 4
    text = render_cognition(0)
    assert assess_cognition(text)["valid"] is True
    assert assess_cognition(render_cognition(0, contradict=True))["valid"] is False
    lowered = text.lower()
    assert "dnd" not in lowered
    assert "dungeons and dragons" not in lowered


def test_a_short_followup_runs_both_passes_without_promoting():
    root = Path(tempfile.mkdtemp())
    receipt = run_planetary_training_passes(
        family_budget=4,
        cognition_steps=2,
        peak_lr=1e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        map_dir=root / "maps",
        cognition_dir=root / "cognition",
        chunk_maps=4,
        chunk_traces=2,
        plateau_rejects=None,
        max_seconds=None,
        ledger_path=None,
    )
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["followups"] == ["tabletop-followup", "jeeves-cognition"]
    maps = receipt["maps"]
    assert maps["budget_met"] is True
    assert maps["selection"] == "tabletop-billion"
    assert maps["per_family_budget"] == 4
    assert set(maps["family_counts"]) == set(FOLLOWUP_FAMILIES)
    assert all(count == 4 for count in maps["family_counts"].values())
    cognition = receipt["cognition"]
    assert cognition["steps_trained"] == 2
    assert cognition["budget_met"] is True
    assert cognition["selection"] == "jeeves-cognition"
    assert cognition["promotion"] is False
    assert "cognition" in cognition["official_tracks"]
    assert isinstance(cognition["cognition_gap_before"], float)
    assert isinstance(cognition["cognition_gap_after"], float)
