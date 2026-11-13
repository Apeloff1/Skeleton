"""Original map variants stay connected, elevated, and off the holdouts."""
from __future__ import annotations

import tempfile
from pathlib import Path

from skeleton.ai.runtime.inference.game_coherent_english import validate_passages
from skeleton.ai.runtime.inference.game_corpus_stream import (
    HOLDOUT_SERIAL,
    TEMPLATES,
    holdout_documents,
    training_serial,
)
from skeleton.ai.runtime.inference.game_focus_finetune import half_weights
from skeleton.ai.runtime.inference.game_map_variants import (
    BILLION_MAPS,
    FAMILIES,
    RESERVED_NAMES,
    assess_map,
    iter_training_maps,
    map_holdouts,
    render_map,
    train_map_budget,
    validate_maps,
)


def test_every_family_has_a_valid_variant_and_no_reserved_name():
    report = validate_maps()
    assert report["families"] == 8
    assert report["checked"] == 32
    assert validate_passages()["domains"] == len(TEMPLATES)
    for family in FAMILIES:
        text = render_map(family, 0)
        judged = assess_map(text)
        assert judged["valid"] is True
        assert judged["family"] == family
        lowered = text.lower()
        for name in RESERVED_NAMES:
            assert name not in lowered
    assert "sea_map" in TEMPLATES
    assert "adventure_map" in TEMPLATES
    assert "homebrew_map" in TEMPLATES
    assert "dungeon_map" in TEMPLATES
    assert "jeeves_cognition" in TEMPLATES
    assert half_weights()["sea_map"] >= 2.0
    assert half_weights()["legal"] == 3.0


def test_elevation_matches_the_variant_and_adventure_stairs_cover_gaps():
    ramp = render_map("elevation_map", 0)
    assert assess_map(ramp)["variant"] == "ramp"
    rows = ramp.splitlines()[1:9]
    assert rows[0].split()[0] == "0"
    assert rows[0].split()[-1] == "9"
    adventure = render_map("adventure_map", 0)
    assert "AB" in adventure.splitlines()
    assert "Stairs" in adventure
    assert assess_map(adventure)["valid"] is True
    cave = render_map("cave_map", 1)
    assert "Walls are not walked" in cave
    assert assess_map(cave)["valid"] is True
    sea = render_map("sea_map", 2)
    assert "~" in sea and "#" in sea
    mountain = render_map("mountain_map", 3)
    assert "^" in mountain and "v" in mountain


def test_training_maps_skip_holdouts_and_cover_every_family():
    reserved = set(map_holdouts()) | set(holdout_documents())
    seen = set()
    count = 0
    for family, text in iter_training_maps(30):
        assert text not in reserved
        assert f"pass {HOLDOUT_SERIAL}." not in text
        assert f"pass {HOLDOUT_SERIAL + 1}." not in text
        assert assess_map(text)["valid"] is True
        seen.add(family)
        count += 1
    assert count == 30
    assert seen == set(FAMILIES)
    assert render_map("sea_map", training_serial(0)) not in reserved


def test_a_short_map_budget_trains_without_promoting():
    root = Path(tempfile.mkdtemp())
    receipt = train_map_budget(
        map_budget=12,
        peak_lr=3e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        checkpoint_dir=root,
        chunk_maps=4,
        plateau_rejects=None,
        ledger_path=None,
    )
    assert receipt["maps_trained"] >= 12
    assert receipt["budget_met"] is True
    assert receipt["stop_reason"] == "budget"
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["byte_loss_is_gameplay_quality"] is False
    assert set(receipt["families"]) == set(FAMILIES)
    assert "maps" in receipt["official_tracks"]
    assert BILLION_MAPS == 1_000_000_000
    homebrew = render_map("homebrew_map", 0)
    tabletop = render_map("tabletop_map", 1)
    dungeon = render_map("dungeon_map", 2)
    assert assess_map(homebrew)["valid"] is True
    assert assess_map(tabletop)["valid"] is True
    assert assess_map(dungeon)["valid"] is True
    assert "Home is one cell" in homebrew
    assert "five feet" in tabletop
    assert "Doors " in dungeon
    blob = "\n".join((homebrew, tabletop, dungeon)).lower()
    for name in ("dnd", "dungeons and dragons", "forgotten realms", "beholder", *RESERVED_NAMES):
        assert name not in blob


def test_a_time_cap_stops_before_the_billion_and_resumes():
    root = Path(tempfile.mkdtemp())
    first = train_map_budget(
        map_budget=BILLION_MAPS,
        peak_lr=1e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        checkpoint_dir=root,
        chunk_maps=4,
        max_seconds=0.01,
        plateau_rejects=None,
        ledger_path=None,
    )
    assert first["budget_met"] is False
    assert first["stop_reason"] == "time"
    assert 0 < first["maps_trained"] < BILLION_MAPS
    assert first["projected_seconds"] > first["seconds"]
    done = int(first["maps_trained"])
    second = train_map_budget(
        map_budget=done + 4,
        peak_lr=1e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        checkpoint_dir=root,
        chunk_maps=4,
        max_seconds=None,
        plateau_rejects=None,
        ledger_path=None,
    )
    assert second["maps_trained"] == done + 4
    assert second["stop_reason"] == "budget"
    assert second["budget_met"] is True
    assert second["maps_kept"] >= first["maps_kept"]
