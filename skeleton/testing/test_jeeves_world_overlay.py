"""Browser overlay: legal choice effects, source proof and safe HTML."""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.evidence import (
    approve_evidence, propose_evidence,
)
from skeleton.jeeves.worlds.factions import (
    approve_factions, propose_factions,
)
from skeleton.jeeves.worlds.overlay import compile_overlay_html
from skeleton.jeeves.worlds.world_canon import CanonError, propose


def world():
    return propose(
        world_id="marsh", premise="An original story with <script> tags.",
        protagonist="Iris", region="Marsh", goal="Reach home.",
    )


def factions(source):
    return approve_factions(propose_factions(
        source, prompt="Earn faction trust.", faction_id="couriers",
        name="Couriers", description="Guild of couriers.",
        choice_id="pursue_goal", delta=12, reason="Reached home."),
        source, "Reviewed original rules.")


def evidence(source):
    return approve_evidence(propose_evidence(
        source, prompt="Discover the note.", clue_id="note",
        title="A note", detail="The truth is <secret>.",
        unlock_choice="pursue_goal"), source, "Reviewed original clue.")


def test_faction_browser_contains_source_derived_playable_rules():
    source = world()
    page = compile_overlay_html(source, factions=factions(source))
    assert "Faction reputation" in page
    assert "choice.from !== scene" in page
    assert "choice.requires.every" in page
    assert "script-src 'sha256-" in page
    assert "connect-src 'none'" in page
    assert page == compile_overlay_html(source, factions=factions(source))
    assert "<script> tags." not in page


def test_clue_browser_never_shows_unearned_spoiler_in_dom_template():
    source = world()
    page = compile_overlay_html(source, evidence=evidence(source))
    assert "Discovered evidence" in page
    assert "collected.has(clue.id)" in page
    assert "textContent = String(value)" in page
    assert "<secret>" not in page
    assert "\\u003csecret>" in page


def test_combined_browser_can_render_both_sources():
    source = world()
    page = compile_overlay_html(
        source, factions=factions(source), evidence=evidence(source))
    assert "Faction reputation" in page
    assert "Discovered evidence" in page


def test_unreviewed_and_stale_sources_fail_closed():
    source = world()
    unreviewed = propose_factions(
        source, prompt="Earn trust", faction_id="couriers",
        name="Couriers", description="Guild", choice_id="pursue_goal",
        delta=5, reason="Earned.")
    with pytest.raises(CanonError, match="faction_review_required"):
        compile_overlay_html(source, factions=unreviewed)
    reviewed = factions(source)
    changed = world()
    changed["prompt"] = "A revised original story."
    with pytest.raises(CanonError, match="faction_world_lease_mismatch"):
        compile_overlay_html(changed, factions=reviewed)


def test_empty_overlay_refused():
    with pytest.raises(CanonError, match="empty_world_overlay"):
        compile_overlay_html(world())


def test_browser_output_budget_fails_closed(monkeypatch):
    from skeleton.jeeves.worlds import overlay as module
    source = world()
    monkeypatch.setattr(module, "_SCRIPT", "x" * 524288)
    with pytest.raises(CanonError, match="overlay_too_large"):
        compile_overlay_html(source, factions=factions(source))
