"""The game corpus covers the required domains and stays off the holdouts."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
    AdaptiveRatchet,
    ByteRNN,
    _scores,
    expand_byte_rnn,
    train_budget,
)
from skeleton.ai.runtime.inference.game_focus_finetune import enterprise_record, half_targets
from skeleton.ai.runtime.inference.game_corpus_stream import (
    BUDGET_BYTES,
    DENYLIST,
    HOLDOUT_GAP,
    HOLDOUT_SERIAL,
    SERIAL_WIDTHS,
    TEMPLATES,
    CorpusStream,
    banned_windows,
    holdout_documents,
    iter_documents,
    leaks,
    render,
    focus_weights,
    track_holdouts,
    training_serial,
    validate_templates,
)


REQUIRED = {
    "legal",
    "coding",
    "sprites",
    "assets",
    "character",
    "world",
    "story",
    "cinematics",
    "cutscenes",
    "cinematic_playwright",
    "playwright",
    "items",
    "clothing",
    "hair",
    "eyes",
}


def test_templates_cover_the_required_domains():
    counts = validate_templates()
    assert counts["domains"] >= 40
    assert REQUIRED <= set(TEMPLATES)
    seen = set()
    stream = CorpusStream()
    for _ in range(len(REQUIRED) * 4):
        domain, text = stream.next_document()
        seen.add(domain)
        assert len(text) >= 40
        assert "Pass " in text
    assert REQUIRED <= seen


def test_stream_respects_a_byte_budget_and_the_denylist():
    assert BUDGET_BYTES == 199 * 1024 * 1024
    banned = banned_windows(DENYLIST)
    reserved = set(holdout_documents())
    produced = 0
    domains = set()
    for domain, text in iter_documents(20_000):
        produced += len(text.encode("utf-8"))
        domains.add(domain)
        assert leaks(text, banned) is False
        assert text not in reserved
        for held in DENYLIST:
            assert held not in text
    assert produced >= 20_000
    assert "legal" in domains
    assert "hair" in domains
    assert "cinematic_playwright" in domains


def test_track_holdouts_are_outside_the_training_serials():
    held = holdout_documents()
    assert len(held) == len(set(held))
    tracks = track_holdouts()
    assert set(tracks) == {"visual", "narrative", "systems", "review", "practice"}
    flat = [text for rows in tracks.values() for text in rows]
    assert set(flat) <= set(held)
    assert len(flat) == len(set(flat))
    # Training serial 0 of each domain is a different line from the reserved holdout.
    for domain in TEMPLATES:
        assert render(domain, 0) not in held


def test_training_serials_practice_long_ids_and_skip_holdouts():
    reserved = {HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1}
    widths = set()
    seen = set()
    for counter in range(5000):
        serial = training_serial(counter)
        assert serial not in reserved
        assert min(abs(serial - HOLDOUT_SERIAL), abs(serial - (HOLDOUT_SERIAL + 1))) >= HOLDOUT_GAP
        widths.add(len(str(serial)))
        seen.add(serial)
    assert widths == set(SERIAL_WIDTHS)
    long_ids = [serial for serial in seen if len(str(serial)) >= 13]
    assert len(long_ids) == len(set(long_ids))
    assert any(len(str(serial)) == 13 for serial in seen)
    held = set(holdout_documents())
    stream = CorpusStream()
    for _ in range(200):
        _domain, text = stream.next_document()
        assert text not in held
        assert "Pass " in text


def test_focus_weights_put_legal_coding_and_review_first():
    weights = focus_weights()
    assert set(weights) == set(TEMPLATES)
    assert weights["legal"] == weights["coding"] == 3.0
    for name in ("proofreading", "syntax", "errors", "crash", "lint"):
        assert weights[name] == 2.5
    assert weights["sprites"] == 1.0
    assert len(TEMPLATES["legal"]) >= 4
    assert len(TEMPLATES["coding"]) >= 4


def test_ratchet_keeps_a_mean_gain_and_blocks_a_track_collapse():
    ratchet = AdaptiveRatchet()
    before = {"visual": 2.0, "narrative": 2.0, "systems": 2.0}
    assert ratchet.observe(before, {name: 1.5 for name in before}) is True
    assert ratchet.margin > 0
    collapsed = {"visual": 1.0, "narrative": 1.0, "systems": 2.5}
    assert ratchet.observe(before, collapsed) is False
    tiny = {name: before[name] - ratchet.margin / 2 for name in before}
    assert ratchet.observe(before, tiny) is False


def test_ratchet_stall_resets_when_a_step_is_kept():
    ratchet = AdaptiveRatchet()
    before = {"visual": 2.0, "narrative": 2.0, "systems": 2.0}
    worse = {name: 2.1 for name in before}
    for _ in range(3):
        assert ratchet.observe(before, worse) is False
    assert ratchet.stall == 3
    assert ratchet.observe(before, {name: 1.5 for name in before}) is True
    assert ratchet.stall == 0


def test_ratchet_shrinks_steps_and_tightens_across_the_cycle():
    ratchet = AdaptiveRatchet()
    before = {"visual": 2.0, "narrative": 2.0, "systems": 2.0}
    worse = {name: 2.1 for name in before}
    scale = ratchet.scale
    locked = ratchet.margin
    for _ in range(4):
        assert ratchet.observe(before, worse) is False
    assert ratchet.scale == scale
    assert ratchet.margin < locked
    assert ratchet.margin >= ratchet.margin_floor
    for _ in range(16):
        assert ratchet.observe(before, worse) is False
    assert ratchet.scale < scale
    assert ratchet.scale >= ratchet.min_scale
    fresh = AdaptiveRatchet()
    assert fresh.tighten(0, 100) > fresh.tighten(50, 100) > fresh.tighten(100, 100)
    assert fresh.scale == fresh.min_scale


def test_another_cycle_continues_from_the_saved_network():
    root = Path(tempfile.mkdtemp())
    first = train_budget(budget_bytes=4096, checkpoint_dir=root, hidden=32, chunk_docs=8)
    second = train_budget(
        additional_bytes=4096,
        peak_lr=3e-4,
        checkpoint_dir=root,
        hidden=32,
        chunk_docs=8,
    )
    assert second["bytes_trained"] >= first["bytes_trained"] + 4096
    assert second["cycle_bytes"] >= 4096
    assert second["promotion"] is False
    assert second["adamw"]["lr"] == 3e-4
    assert set(first["mastery"]) <= set(second["mastery"])
    assert second["schema"] == "skeleton.game_adaptive_ratchet.v2"


def test_a_short_budget_trains_without_promoting():
    root = Path(tempfile.mkdtemp())
    receipt = train_budget(budget_bytes=8192, checkpoint_dir=root, hidden=32, chunk_docs=16)
    assert receipt["bytes_trained"] >= 8192
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["byte_loss_is_gameplay_quality"] is False
    assert receipt["adamw"]["betas"] == [0.9, 0.999]
    assert receipt["adamw"]["weight_decay"] == 0.01
    assert set(receipt["official_tracks"]) == {"visual", "narrative", "systems", "review", "practice"}


def test_score_ceiling_stops_before_the_budget():
    root = Path(tempfile.mkdtemp())
    receipt = train_budget(
        budget_bytes=200_000,
        checkpoint_dir=root,
        hidden=16,
        chunk_docs=4,
        score_ceiling={name: 100.0 for name in ("visual", "narrative", "systems", "review", "practice")},
    )
    assert receipt["bytes_trained"] == 0
    assert receipt["promotion"] is False
    assert set(receipt["official_tracks"]) == {"visual", "narrative", "systems", "review", "practice"}


def test_widening_keeps_the_current_holdouts_and_records_the_half():
    small = ByteRNN(8)
    wide = expand_byte_rnn(small, 16)
    tracks = {name: rows[:2] for name, rows in track_holdouts().items()}
    before = _scores(small, tracks)
    after = _scores(wide, tracks)
    for name in before:
        assert abs(before[name] - after[name]) < 1e-4
    baseline = {"visual": 1.5, "narrative": 1.4}
    assert half_targets(baseline) == {"visual": 0.75, "narrative": 0.7}
    record = enterprise_record(
        baseline=baseline,
        official={"visual": 1.2, "narrative": 1.1},
        rollback_digest="a" * 64,
    )
    assert record["enterprise_qualified"] is False
    assert record["standardized"] is True
    assert record["half_met_all"] is False
    assert record["promotion"] is False
    assert set(record["levels"]) == {f"L{i:02d}" for i in range(14)}


def test_transformer_finetune_stays_off_the_serving_checkpoint():
    from skeleton.ai.runtime.inference.game_focus_finetune import finetune_transformer

    root = Path(tempfile.mkdtemp())
    receipt = finetune_transformer(max_documents=4, checkpoint_dir=root)
    assert receipt["promotion"] is False
    assert receipt["service_checkpoint_touched"] is False
    assert receipt["documents"] == 4
    assert math.isfinite(receipt["holdout_logprob_before"])
    assert math.isfinite(receipt["holdout_logprob_after"])
    assert set(receipt["review_domains"]) == {"proofreading", "syntax", "errors", "crash", "lint"}
