"""The real reviewed-knowledge ledger is the Dragon egg/XP input authority."""
from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.game_builder.reviewed_knowledge import (
    KnowledgeError, ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.webcrawler.dragon_nest_review_bridge import DragonNestReviewBridge
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore

OWNER = "nest-test-owner"
T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"


@pytest.fixture
def setup_review(tmp_path):
    library = ReviewedKnowledgeStore(tmp_path / "knowledge.sqlite")
    db = sqlite3.connect(":memory:")
    nest = DragonNestStore(db, signing_key=b"nest-review-test-key-32-bytes-long!")
    nest.initialize(OWNER, ("article-a", "video-b"),
                    focus_tags=("movement",), adjacent_tags=("physics",),
                    at=T0, authorized=True)

    def document(source, host, group, at=T0, active=True):
        notes = (ReviewedNote(
            "review-1", "movement", "Movement improves game control.", 0, 8,
            "supports", 975000, group, ("movement",),
        ),) if active else ()
        return ReviewedDocument(
            OWNER, source, f"https://{host}/study",
            "Movement study", "Movement in original games.", at,
            "rights-reference", ("design_reference",), "independent-reviewer",
            active, notes, "active" if active else "retracted",
        )

    a = library.import_document(
        document("article-a", "research.example.org", "group-a"),
        expected_parent_digest=None, authorized=True,
    )
    b = library.import_document(
        document("video-b", "www.youtube.com", "group-b"),
        expected_parent_digest=None, authorized=True,
    )
    bridge = DragonNestReviewBridge(library, nest)
    try:
        yield bridge, nest, library, document, (a, b)
    finally:
        library.close()
        db.close()


def verified_brief(library):
    return library.build_brief(
        OWNER, "movement", authorized=True,
        min_independent_groups=2, min_confidence_ppm=800000,
    )


def adult(bridge, nest, library):
    brief = verified_brief(library)
    bridge.feed_parent(OWNER, brief, "article-a", at=T0, authorized=True)
    return bridge.feed_parent(OWNER, brief, "video-b", at=T0, authorized=True)


def test_reviewed_source_history_grows_exactly_three_hatchlings(setup_review):
    bridge, nest, library, _, _ = setup_review
    finished = adult(bridge, nest, library)
    assert finished.stage == "adult"
    assert [child.lane for child in finished.children] == [
        "article", "video", "updates",
    ]
    brief = verified_brief(library)
    first = bridge.feed_idle(
        OWNER, brief, "article-a", lane="article", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
    )
    second = bridge.feed_idle(
        OWNER, brief, "video-b", lane="video", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
    )
    latest = library.history(OWNER, "article-a", authorized=True)[-1]
    library.import_document(
        replace(setup_review[3]("article-a", "research.example.org", "group-a",
                                at=T1),
                text="Movement engines in original games."),
        expected_parent_digest=latest.revision_digest, authorized=True,
    )
    revised_brief = verified_brief(library)
    third = bridge.feed_idle(
        OWNER, revised_brief, "article-a", lane="updates", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
        published_at="2026-10-12T12:05:00Z",
    )
    assert [child.level for child in third.children] == [1, 1, 1]
    assert nest.read(OWNER, authorized=True) == third
    assert all(change.improvement.startswith("(") for change in third.changes)
    assert bridge.feed_idle(
        OWNER, revised_brief, "article-a", lane="updates", at=T1,
        idle_since=T0, consented=True, background_allowed=True,
        authorized=True, published_at="2026-10-12T12:05:00Z",
    ) == third


def test_updates_require_a_genuinely_changed_reviewed_source_revision(setup_review):
    bridge, nest, library, document, receipts = setup_review
    adult(bridge, nest, library)
    initial_brief = verified_brief(library)
    with pytest.raises(ValueError, match="changed reviewed"):
        bridge.feed_idle(
            OWNER, initial_brief, "article-a", lane="updates", at=T1,
            idle_since=T0, consented=True,
            background_allowed=True, authorized=True,
            published_at="2026-10-12T12:05:00Z",
        )
    # A rereview that changes metadata but not bytes is not an update.
    library.import_document(
        document("article-a", "research.example.org", "group-a", at=T1),
        expected_parent_digest=receipts[0].revision_digest, authorized=True,
    )
    with pytest.raises(ValueError, match="changed reviewed"):
        bridge.feed_idle(
            OWNER, verified_brief(library), "article-a", lane="updates",
            at="2026-10-12T12:20:00Z", idle_since=T0, consented=True,
            background_allowed=True, authorized=True,
            published_at="2026-10-12T12:05:00Z",
        )
    assert nest.read(OWNER, authorized=True).children[2].level == 0


def test_no_cross_media_or_no_independent_review(setup_review):
    bridge, nest, library, _, _ = setup_review
    adult(bridge, nest, library)
    brief = verified_brief(library)
    with pytest.raises(ValueError, match="video source"):
        bridge.feed_idle(
            OWNER, brief, "article-a", lane="video", at=T1, idle_since=T0,
            consented=True, background_allowed=True, authorized=True,
        )
    with pytest.raises(ValueError, match="article"):
        bridge.feed_idle(
            OWNER, brief, "video-b", lane="article", at=T1, idle_since=T0,
            consented=True, background_allowed=True, authorized=True,
        )
    with pytest.raises(ValueError, match="independent"):
        bridge.feed_parent(OWNER, None, "article-a", at=T1, authorized=True)


def test_retracted_revision_invalidates_historical_growth_permission(setup_review):
    bridge, nest, library, document, receipts = setup_review
    adult(bridge, nest, library)
    previous = verified_brief(library)
    library.import_document(
        document("article-a", "research.example.org", "group-a",
                 at=T1, active=False),
        expected_parent_digest=receipts[0].revision_digest, authorized=True,
    )
    with pytest.raises(KnowledgeError, match="changed"):
        bridge.feed_idle(
            OWNER, previous, "article-a", lane="article",
            at="2026-10-12T12:20:00Z", idle_since=T0,
            consented=True, background_allowed=True, authorized=True,
        )
    assert all(child.level == 0 for child in nest.read(OWNER, authorized=True).children)


def test_idle_resource_and_consent_cannot_be_bypassed_by_reviewed_brief(setup_review):
    bridge, nest, library, _, _ = setup_review
    adult(bridge, nest, library)
    brief = verified_brief(library)
    for consent, resources in ((False, True), (True, False)):
        with pytest.raises(PermissionError):
            bridge.feed_idle(
                OWNER, brief, "article-a", lane="article",
                at=T1, idle_since=T0,
                consented=consent, background_allowed=resources, authorized=True,
            )
    assert nest.view(OWNER, authorized=True)["children"][0]["level"] == 0


def test_untrusted_or_cross_owner_handoff_does_not_write(setup_review):
    bridge, nest, library, _, _ = setup_review
    brief = verified_brief(library)
    with pytest.raises(PermissionError):
        bridge.feed_parent(OWNER, brief, "article-a", at=T0, authorized=False)
    with pytest.raises(ValueError):
        bridge.feed_parent("other-owner", brief, "article-a", at=T0, authorized=True)
    assert nest.view(OWNER, authorized=True)["sources_consumed"] == 0


def test_mother_automatically_gleans_every_idle_child_event_without_duplicate_xp(setup_review):
    from skeleton.ai.webcrawler.dragon_mother_glean_ledger import MotherGleanLedger
    bridge, nest, library, _, _ = setup_review
    mother = MotherGleanLedger(
        nest.db, signing_key=b"mother-child-integration-key-32-bytes-long",
    )
    automatic = DragonNestReviewBridge(library, nest, mother_ledger=mother)
    adult(automatic, nest, library)
    brief = verified_brief(library)
    one = automatic.feed_idle(
        OWNER, brief, "article-a", lane="article", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
    )
    assert one.children[0].level == 1
    assert len(mother.history(OWNER, authorized=True)) == 1
    assert len(mother.history(OWNER, authorized=True)[0].probes) == 36
    two = automatic.feed_idle(
        OWNER, brief, "video-b", lane="video", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
    )
    assert two.children[1].level == 1
    assert len(mother.history(OWNER, authorized=True)) == 2
    retry = automatic.feed_idle(
        OWNER, brief, "article-a", lane="article", at=T1, idle_since=T0,
        consented=True, background_allowed=True, authorized=True,
    )
    assert retry == two
    assert len(mother.history(OWNER, authorized=True)) == 2
    assert all(not r.promotion_authorized for r in mother.history(
        OWNER, authorized=True,
    ))


def test_failed_mother_ledger_run_recovers_on_same_child_event_retry(setup_review,monkeypatch):
    from skeleton.ai.webcrawler.dragon_mother_glean_ledger import MotherGleanLedger
    bridge, nest, library, _, _ = setup_review
    mother = MotherGleanLedger(
        nest.db, signing_key=b"mother-recovery-integration-key-32byteslong",
    )
    automatic = DragonNestReviewBridge(library, nest, mother_ledger=mother)
    adult(automatic, nest, library)
    brief = verified_brief(library)
    original_run = mother.run
    attempts = {"count": 0}

    def interrupted(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("temporary mother glean checkpoint failure")
        return original_run(*args, **kwargs)

    monkeypatch.setattr(mother, "run", interrupted)
    with pytest.raises(ValueError, match="checkpoint failure"):
        automatic.feed_idle(
            OWNER, brief, "article-a", lane="article",
            at=T1, idle_since=T0, consented=True,
            background_allowed=True, authorized=True,
        )
    assert nest.read(OWNER, authorized=True).children[0].level == 1
    assert mother.history(OWNER, authorized=True) == ()
    repeated = automatic.feed_idle(
        OWNER, brief, "article-a", lane="article",
        at=T1, idle_since=T0, consented=True,
        background_allowed=True, authorized=True,
    )
    assert repeated.children[0].level == 1
    assert len(mother.history(OWNER, authorized=True)) == 1
    assert attempts["count"] == 2
