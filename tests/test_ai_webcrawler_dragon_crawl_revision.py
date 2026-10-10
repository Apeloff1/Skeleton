"""Revision drift and quote relocation tests for recrawled evidence."""
from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.dragon_crawl_custody import (
    CapturedSource, CustodyPolicy, LocatedReading,
)
from skeleton.ai.webcrawler.dragon_crawl_revision import (
    ReadingDisposition, SourceChange, compare_crawl_revisions,
)


def capture(sid, text="A claim sentence about jump buffering was observed.",
            *, path="/article"):
    url = f"https://{sid}.example{path}"
    doc = extract_document(
        FetchResponse(url, 200, {"content-type": "text/plain"},
                      text.encode("utf-8"), 1700000000.0),
        url,
    )
    assert doc is not None
    return CapturedSource(sid, doc)


def reading(sid="alpha", number=1):
    return LocatedReading(
        sid, f"pass-{number}", "claim", True, .8, .9, 0, 16,
    )


def check(previous, readings, current, **kwargs):
    return compare_crawl_revisions(
        "claim", previous, readings, current, authorized=True, **kwargs,
    )


def test_identical_recrawl_preserves_content_anchored_passages():
    first = (capture("alpha"), capture("beta"))
    result = check(first, (reading("alpha"), reading("beta")), first)
    assert result.prior_readings_reusable
    assert result.invalidated_readings == 0
    assert all(x.change is SourceChange.UNCHANGED for x in result.sources)
    assert all(x.disposition is ReadingDisposition.REUSABLE
               for x in result.readings)
    assert all(x.candidate_span == (0, 16) for x in result.readings)


def test_new_fetched_time_with_same_content_does_not_invalidate_passages():
    old = capture("alpha")
    new_doc = replace(
        old.document,
        fetched_at=1700000040.0,
        provenance={**old.document.provenance, "fetched_at": 1700000040.0},
    )
    report = check((old,), (reading(),),
                   (replace(old, document=new_doc),))
    assert report.prior_readings_reusable
    assert report.invalidated_readings == 0
    assert report.original_custody_fingerprint != report.current_custody_fingerprint


def test_new_content_with_unique_old_quote_requires_new_review():
    old = capture("alpha")
    fresh = capture(
        "alpha",
        "New preceding heading. A claim sentence about jump buffering was observed.",
    )
    result = check((old,), (reading(),), (fresh,))
    assert not result.prior_readings_reusable
    assert result.sources[0].content_changed
    assert result.readings[0].disposition is (
        ReadingDisposition.REASSESS_REVISED_DOCUMENT
    )
    assert result.readings[0].candidate_span == (23, 39)
    assert result.readings[0].matching_quotes == 1


def test_removed_quote_cannot_be_relocated_by_guessing():
    report = check(
        (capture("alpha"),), (reading(),),
        (capture("alpha", "Completely different source statement."),),
    )
    assert report.readings[0].disposition is ReadingDisposition.QUOTE_ABSENT
    assert report.readings[0].candidate_span is None
    assert report.readings[0].matching_quotes == 0


def test_duplicate_quote_never_chooses_arbitrary_location():
    report = check(
        (capture("alpha"),), (reading(),),
        (capture("alpha", "A claim sentence, then A claim sentence repeated."),),
    )
    assert report.readings[0].disposition is ReadingDisposition.QUOTE_AMBIGUOUS
    assert report.readings[0].candidate_span is None
    assert report.readings[0].matching_quotes == 2


def test_new_origin_with_same_text_is_not_silently_reused():
    original = capture("alpha")
    moved = capture("alpha", path="/different-source")
    report = check((original,), (reading(),), (moved,))
    assert report.readings[0].disposition is ReadingDisposition.ORIGIN_CHANGED
    assert report.sources[0].origin_changed
    assert not report.prior_readings_reusable


def test_derivation_lineage_change_invalidates_even_identical_content():
    alpha, beta = capture("alpha"), capture("beta")
    fresh_alpha = replace(alpha, parent_source_ids=("beta",))
    report = check(
        (alpha, beta), (reading(),),
        (fresh_alpha, beta),
    )
    assert report.sources[0].lineage_changed
    assert report.readings[0].disposition is ReadingDisposition.LINEAGE_CHANGED


def test_missing_source_reported_instead_of_ghost_verification():
    alpha = capture("alpha")
    result = check((alpha,), (reading(),), ())
    assert not result.prior_readings_reusable
    assert result.missing_sources == ("alpha",)
    assert result.invalidated_readings == 1
    assert result.readings[0].disposition is ReadingDisposition.MISSING_SOURCE
    assert result.sources[0].change is SourceChange.MISSING
    assert not result.sources[0].content_changed


def test_new_sources_must_be_reviewed_before_reuse_decision():
    alpha = capture("alpha")
    report = check((alpha,), (reading(),), (alpha, capture("beta")))
    assert not report.prior_readings_reusable
    assert report.added_sources == ("beta",)
    assert report.sources[-1].change is SourceChange.NEW
    assert report.invalidated_readings == 0


def test_empty_reading_set_is_not_reusable_knowledge():
    alpha = capture("alpha")
    report = check((alpha,), (), (alpha,))
    assert not report.prior_readings_reusable
    assert report.invalidated_readings == 0
    assert report.readings == ()


def test_fingerprints_change_when_source_revision_changes():
    original = capture("alpha")
    before = check((original,), (reading(),), (original,))
    after = check(
        (original,), (reading(),),
        (capture("alpha", "Edited newer article about something else."),),
    )
    assert before.fingerprint != after.fingerprint
    assert before.current_custody_fingerprint != after.current_custody_fingerprint
    assert not after.prior_readings_reusable
    assert after.sources[0].quality_changed
    assert after.readings[0].disposition is ReadingDisposition.QUOTE_ABSENT
    assert after.readings[0].requires_human_review


def test_permutation_does_not_change_any_revision_receipt():
    sources = (capture("alpha"), capture("beta"))
    changed = (
        capture("alpha", "More content. A claim sentence about jump buffering was observed."),
        sources[1],
    )
    evidence = (reading("alpha"), reading("beta"))
    a = check(sources, evidence, changed)
    b = check(tuple(reversed(sources)), tuple(reversed(evidence)),
              tuple(reversed(changed)))
    assert a == b


def test_invalid_new_capture_fails_closed_before_comparison():
    alpha = capture("alpha")
    poisoned = replace(alpha.document, text="Altered without hashing")
    with pytest.raises(ValueError, match="content hash mismatch"):
        check(
            (alpha,), (reading(),),
            (replace(alpha, document=poisoned),),
        )


def test_current_inventory_parent_custody_must_remain_complete():
    alpha, beta = capture("alpha"), capture("beta")
    orphan = replace(alpha, parent_source_ids=("beta",))
    with pytest.raises(ValueError, match="undeclared captured source parent"):
        check((alpha,), (reading(),), (orphan,))


def test_cross_claim_source_reading_is_not_compared():
    alpha = capture("alpha")
    mismatched = replace(reading(), claim_id="different")
    with pytest.raises(ValueError, match="cross-claim"):
        check((alpha,), (mismatched,), (alpha,))


def test_custody_budget_rejects_unbounded_before_and_after_inventories():
    sources = (capture("alpha"), capture("beta"))
    with pytest.raises(ValueError, match="capacity"):
        check(sources, (reading("alpha"),), sources,
              custody_policy=CustodyPolicy(max_sources=1))


def test_revision_comparison_requires_explicit_authorization():
    alpha = capture("alpha")
    with pytest.raises(PermissionError):
        compare_crawl_revisions(
            "claim", (alpha,), (reading(),), (alpha,), authorized=False,
        )


def test_redirect_delivery_identity_change_invalidates_unmodified_text():
    alpha = capture("alpha")
    updated_doc = replace(
        alpha.document, fetched_url="https://cdn.example/article",
        provenance={
            **alpha.document.provenance,
            "fetched_url": "https://cdn.example/article",
        },
    )
    review = check((alpha,), (reading(),),
                   (replace(alpha, document=updated_doc),))
    assert review.sources[0].delivery_changed
    assert review.readings[0].disposition is ReadingDisposition.DELIVERY_CHANGED
    assert not review.prior_readings_reusable


def test_reordered_custody_lineage_is_semantically_equivalent():
    alpha = capture("alpha")
    original = replace(alpha, lineage_tokens=("camera", "level"))
    reordered = replace(alpha, lineage_tokens=("level", "camera"))
    review = check((original,), (reading(),), (reordered,))
    assert review.prior_readings_reusable
    assert not review.sources[0].lineage_changed
    assert review.sources[0].change is SourceChange.UNCHANGED
    # Original custody includes readings; the current inventory deliberately does not.


def test_public_crawler_namespace_exposes_revision_review():
    from skeleton.ai import webcrawler
    assert webcrawler.compare_crawl_revisions is compare_crawl_revisions
    assert webcrawler.SourceChange is SourceChange
    assert webcrawler.ReadingDisposition is ReadingDisposition


def test_nonobserved_source_revision_also_revokes_whole_claim_reuse():
    alpha, beta = capture("alpha"), capture("beta")
    new_beta = capture("beta", "Entirely new source section without old language.")
    verdict = check((alpha, beta), (reading("alpha"),), (alpha, new_beta))
    assert verdict.invalidated_readings == 0
    assert verdict.readings[0].disposition is ReadingDisposition.REUSABLE
    assert verdict.sources[-1].change is SourceChange.CHANGED
    assert not verdict.prior_readings_reusable


def test_modified_nonobserved_parent_invalidates_descendant_claim():
    alpha = capture("alpha")
    beta = capture("beta")
    child = replace(alpha, parent_source_ids=("beta",))
    new_beta = capture("beta", "Modified parent study version.")
    verdict = check((child, beta), (reading("alpha"),), (child, new_beta))
    assert not verdict.prior_readings_reusable
    assert verdict.readings[0].disposition is ReadingDisposition.REUSABLE
    assert verdict.sources[-1].content_changed


def test_acquisition_metadata_changes_custody_digest_but_not_verified_quote():
    alpha = capture("alpha")
    new_doc = replace(
        alpha.document,
        source_score=alpha.document.source_score - .1,
    )
    updated = replace(alpha, document=new_doc)
    before = check((alpha,), (reading(),), (alpha,))
    after = check((alpha,), (reading(),), (updated,))
    assert before.current_custody_fingerprint != after.current_custody_fingerprint


def test_status_change_requires_new_acquisition_policy_review():
    alpha = capture("alpha")
    updated = replace(
        alpha.document,
        provenance={**alpha.document.provenance, "status": 206},
    )
    result = check((alpha,), (reading(),),
                   (replace(alpha, document=updated),))
    assert result.sources[0].quality_changed
    assert result.readings[0].disposition is ReadingDisposition.QUALITY_CHANGED
    assert not result.prior_readings_reusable


def test_acquisition_extension_change_requires_quality_review():
    alpha = capture("alpha")
    provenance = {**alpha.document.provenance, "retention_class": "restricted"}
    updated = replace(alpha, document=replace(
        alpha.document, provenance=provenance,
    ))
    result = check((alpha,), (reading(),), (updated,))
    assert result.sources[0].quality_changed
    assert result.invalidated_readings == 1
    assert result.readings[0].disposition is ReadingDisposition.QUALITY_CHANGED


def test_capture_time_only_change_is_not_quality_drift():
    alpha = capture("alpha")
    updated = replace(alpha, document=replace(
        alpha.document,
        fetched_at=alpha.document.fetched_at + 60,
        provenance={
            **alpha.document.provenance,
            "fetched_at": alpha.document.fetched_at + 60,
        },
    ))
    result = check((alpha,), (reading(),), (updated,))
    assert not result.sources[0].quality_changed
    assert result.sources[0].change is SourceChange.UNCHANGED
    assert result.prior_readings_reusable
