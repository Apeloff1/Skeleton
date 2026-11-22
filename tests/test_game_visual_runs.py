"""Visual runs cover the corpus and keep copyright avoidance on every variant."""
from __future__ import annotations

import tempfile
from pathlib import Path

from skeleton.ai.runtime.inference.game_corpus_stream import TEMPLATES, domains
from skeleton.ai.runtime.inference.game_visual_runs import (
    BILLION_RUNS,
    ELEMENTS,
    SHADOWS,
    STYLE_NAMES,
    WEATHERS,
    assess_visual_run,
    iter_visual_runs,
    render_visual_run,
    train_visual_runs,
    validate_visual_runs,
)
from skeleton.ai.runtime.inference.game_map_variants import RESERVED_NAMES


def test_every_domain_has_an_original_picture_and_a_copyright_line():
    report = validate_visual_runs()
    assert report["domains"] == len(TEMPLATES) == len(domains())
    covered = {assess_visual_run(render_visual_run(serial))["domain"] for serial in range(len(domains()))}
    assert covered == set(domains())
    elements, shadows, weathers = set(), set(), set()
    for _domain, text in iter_visual_runs(24):
        judged = assess_visual_run(text)
        assert judged["valid"] is True
        assert "does not copy a commercial frame" in text
        assert "names the author" in text
        elements.add(judged["element"])
        shadows.add(judged["shadow"])
        weathers.add(judged["weather"])
        lowered = text.lower()
        for name in (*RESERVED_NAMES, *STYLE_NAMES, "dnd"):
            assert name not in lowered
    assert elements <= set(ELEMENTS) and elements
    assert shadows <= set(SHADOWS) and shadows
    assert weathers <= set(WEATHERS) and weathers
    assert BILLION_RUNS == 1_000_000_000
    assert "visual_run" in TEMPLATES


def test_a_short_visual_budget_trains_without_promoting():
    root = Path(tempfile.mkdtemp())
    receipt = train_visual_runs(
        run_budget=12,
        peak_lr=1e-5,
        hidden=16,
        source=None,
        expected_digest=None,
        checkpoint_dir=root,
        chunk_runs=4,
        plateau_rejects=None,
        max_seconds=None,
        ledger_path=None,
    )
    assert receipt["runs_trained"] >= 12
    assert receipt["budget_met"] is True
    assert receipt["stop_reason"] == "budget"
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["byte_loss_is_gameplay_quality"] is False
    assert receipt["selection"] == "visual-billion"
    assert "visual_runs" in receipt["official_tracks"]
    assert set(receipt["domains_seen"]) <= set(domains())
    assert render_visual_run(0) != render_visual_run(1)
