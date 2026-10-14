"""The Dragon egg game is a passive reducer; no test performs a crawl."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.webcrawler.dragon_nest_progression import (
    AcquiredKnowledge, LANES, feed_parent, learn_when_idle, nest_snapshot,
    new_nest, verify_change_history,
)

T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"
H1 = "a" * 64
H2 = "b" * 64


def nest(count=2):
    return new_nest("test-user", tuple("source-" + str(n) for n in range(count)),
                    focus_tags=("game-code",), adjacent_tags=("software-debug",), at=T0)


def adult():
    dragon = nest()
    dragon = feed_parent(dragon, "source-0", content_sha256=H1, at=T0,
                         authorized=True, reviewed=True, lawful=True)
    dragon = feed_parent(dragon, "source-1", content_sha256=H2, at=T0,
                         authorized=True, reviewed=True, lawful=True)
    return dragon


def knowledge(digest=H1, *, source="library/a", tags=("game-code",),
              published="2026-10-11T00:00:00Z", reviewed=True, lawful=True,
              observed=T1, confidence=0.95, kind="article"):
    return AcquiredKnowledge(source, digest, observed, tags, reviewed, lawful,
                             confidence, published, kind)


def grow(dragon, lane="article", item=None, **kw):
    return learn_when_idle(dragon, lane, item or knowledge(), at=kw.pop("at", T1),
                           idle_since=kw.pop("idle_since", T0), consented=kw.pop("consented", True),
                           background_allowed=kw.pop("background_allowed", True),
                           owner_authorized=kw.pop("owner_authorized", True), **kw)


def test_parent_requires_finite_stable_inventory_and_creates_exactly_three_eggs():
    dragon = nest()
    assert dragon.stage == "egg" and dragon.children == ()
    midway = feed_parent(dragon, "source-0", content_sha256=H1, at=T0,
                         authorized=True, reviewed=True, lawful=True)
    assert midway.stage != "adult" and midway.children == ()
    finished = feed_parent(midway, "source-1", content_sha256=H2, at=T0,
                           authorized=True, reviewed=True, lawful=True)
    assert finished.stage == "adult" and finished.level == 20
    assert tuple(child.lane for child in finished.children) == LANES
    assert all(child.stage == "egg" for child in finished.children)
    assert verify_change_history(finished)
    assert grow(finished).children[0].stage == "hatchling"


def test_duplicate_parent_source_cannot_multiply_level_or_eggs():
    first = adult()
    duplicate = feed_parent(first, "source-1", content_sha256=H1, at=T1,
                            authorized=True, reviewed=True, lawful=True)
    assert first == duplicate and len(first.children) == 3


@pytest.mark.parametrize("kwargs,error", [
    ({"authorized": False, "reviewed": True, "lawful": True}, PermissionError),
    ({"authorized": True, "reviewed": False, "lawful": True}, PermissionError),
    ({"authorized": True, "reviewed": True, "lawful": False}, PermissionError),
])
def test_parent_cannot_grow_from_unapproved_material(kwargs, error):
    with pytest.raises(error):
        feed_parent(nest(), "source-0", content_sha256=H1, at=T0, **kwargs)


def test_unknown_or_forged_census_sources_rejected():
    with pytest.raises(ValueError):
        new_nest("owner", ("x", "x"), focus_tags=("game-code",), at=T0)
    with pytest.raises(ValueError):
        feed_parent(nest(), "unlisted", content_sha256=H1, at=T1,
                    authorized=True, reviewed=True, lawful=True)
    with pytest.raises(ValueError):
        new_nest("owner", (), focus_tags=("game-code",), at=T0)


@pytest.mark.parametrize("overrides", [
    {"consented": False},
    {"owner_authorized": False},
    {"background_allowed": False},
    {"idle_since": "2026-10-12T12:09:59Z"},
    {"idle_since": "2026-10-12T12:20:00Z"},
])
def test_hatchlings_do_not_work_without_actual_idle_authorization(overrides):
    with pytest.raises(PermissionError):
        grow(adult(), **overrides)


@pytest.mark.parametrize("item,error", [
    (knowledge(reviewed=False), PermissionError),
    (knowledge(lawful=False), PermissionError),
    (knowledge(confidence=0.79), ValueError),
    (knowledge(confidence=float("nan")), ValueError),
    (knowledge(tags=("unrelated",)), ValueError),
    (knowledge(observed="2025-01-01T00:00:00Z"), ValueError),
    (knowledge(observed="2026-10-13T00:00:00Z"), ValueError),
    (knowledge(digest="bad"), ValueError),
])
def test_hatchling_requires_verified_novel_task_knowledge(item, error):
    with pytest.raises(error):
        grow(adult(), item=item)


def test_article_video_updates_are_isolated_and_adjacent_knowledge_counts():
    dragon = adult()
    dragon = grow(dragon, "article", knowledge(source="docs/a", tags=("software-debug",)))
    assert dragon.children[0].level == 1
    assert dragon.children[1].level == 0
    assert "adjacent-relevant" in dragon.changes[-1].improvement
    dragon = grow(dragon, "video", knowledge(source="video/v", digest=H2, kind="video"))
    dragon = grow(dragon, "updates", knowledge(source="upstream/r", digest=H2, kind="updates"))
    assert [child.level for child in dragon.children] == [1, 1, 1]
    assert all(child.stage == "hatchling" for child in dragon.children)
    assert verify_change_history(dragon)


def test_specialists_refuse_cross_lane_evidence():
    with pytest.raises(ValueError, match="media kind"):
        grow(adult(), "video", knowledge(kind="article"))
    with pytest.raises(ValueError, match="media kind"):
        grow(adult(), "updates", knowledge(kind="video"))


def test_updates_require_dated_recent_revisions():
    with pytest.raises(ValueError):
        grow(adult(), "updates", knowledge(published=None, kind="updates"))
    with pytest.raises(ValueError):
        grow(adult(), "updates", knowledge(published="2020-01-01T00:00:00Z", kind="updates"))
    with pytest.raises(ValueError):
        grow(adult(), "updates", knowledge(published="2026-10-12T15:00:00Z", kind="updates"))


def test_duplicate_evidence_retry_does_not_increase_level_or_history():
    dragon = grow(adult())
    assert grow(dragon) == dragon
    updated = grow(dragon, item=knowledge(digest=H2))
    assert len(updated.children[0].evidence) == 2
    assert len(updated.changes) == len(dragon.changes) + 1


def test_old_source_revision_does_not_replace_newer_information():
    state = grow(adult())
    old = knowledge(digest=H2, observed="2026-10-12T12:01:00Z")
    with pytest.raises(ValueError, match="regressed"):
        grow(state, item=old)


def test_change_history_detects_tampering_and_provides_ui_receipts():
    dragon = grow(adult())
    ui = nest_snapshot(dragon)
    assert ui["schema"] == "skeleton.dragon.nest.v1"
    assert ui["sources_consumed"] == 2
    assert ui["promotion_authorized"] is False
    assert ui["history_head"] == dragon.head
    assert ui["last_changed_at"].endswith("Z")
    assert ui["last_improvement"].startswith("(")
    corrupted = replace(dragon, changes=dragon.changes[:-1] +
                        (replace(dragon.changes[-1], improvement="(fabricated)"),))
    assert not verify_change_history(corrupted)
    with pytest.raises(ValueError, match="verification"):
        nest_snapshot(corrupted)


def test_history_forbids_backdated_changes_and_naive_time():
    with pytest.raises(ValueError):
        new_nest("owner", ("a",), focus_tags=("game-code",), at="2026-10-12T12:00:00")
    with pytest.raises(ValueError):
        feed_parent(nest(), "source-0", content_sha256=H1,
                    at="2026-10-11T13:00:00Z", authorized=True,
                    reviewed=True, lawful=True)


def test_stage_levels_bounded_under_continuous_novel_evidence():
    dragon = adult()
    for n in range(202):
        item = knowledge(digest=f"{n:064x}", source=f"research/{n}")
        dragon = grow(dragon, "article", item)
    assert dragon.children[0].level == 20
    assert dragon.children[0].stage == "adult"
    assert len(dragon.children[0].evidence) == 202
    assert verify_change_history(dragon)


def test_change_history_commits_final_state_not_only_change_prose():
    dragon = grow(adult())
    assert verify_change_history(dragon)
    assert len(dragon.changes[-1].state_digest) == 64
    changes = (
        replace(dragon, consumed=()),
        replace(dragon, level=0),
        replace(dragon, stage="egg"),
        replace(dragon, catalog_digest="f" * 64),
        replace(dragon, children=dragon.children[:1]),
        replace(dragon, children=(
            replace(dragon.children[0], level=19),
            *dragon.children[1:],
        )),
        replace(dragon, source_ids=("forged-source",)),
        replace(dragon, focus_tags=("spoofed-relevance",)),
    )
    for forged in changes:
        assert not verify_change_history(forged)
        with pytest.raises(ValueError, match="verification"):
            nest_snapshot(forged)


def test_change_history_rejects_modified_state_receipt_even_with_existing_head():
    dragon = adult()
    bad_entry = replace(dragon.changes[-1], state_digest="e" * 64)
    assert not verify_change_history(
        replace(dragon, changes=(*dragon.changes[:-1], bad_entry))
    )
