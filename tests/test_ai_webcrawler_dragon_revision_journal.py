"""SQLite revision-journal reliability, fencing, owner isolation and tamper tests."""
from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.dragon_crawl_custody import CapturedSource, LocatedReading
from skeleton.ai.webcrawler.dragon_crawl_revision import compare_crawl_revisions
from skeleton.ai.webcrawler.dragon_revision_journal import RevisionJournal


def capture(text="Evidence statement recorded at source."):
    url = "https://journal.example/primary"
    response = FetchResponse(
        url, 200, {"content-type": "text/plain"},
        text.encode(), 1700000000.0,
    )
    doc = extract_document(response, url)
    assert doc is not None
    return CapturedSource("primary", doc)


def reading():
    return LocatedReading("primary", "pass-1", "claim-42", True, .8, .9, 0, 8)


def report(*, current=None):
    source = capture()
    return compare_crawl_revisions(
        "claim-42", (source,), (reading(),),
        (current or source,), authorized=True,
    )


def ledger(max_per_claim=100000):
    return RevisionJournal(sqlite3.connect(":memory:"), max_per_claim=max_per_claim)


def test_first_append_is_verifiable_and_latest_matches_entry():
    journal = ledger()
    review = report()
    entry = journal.append(
        "owner-a", review, observed_at=12.5, expected_sequence=0,
        authorized=True,
    )
    assert entry.sequence == 1
    assert entry.review_fingerprint == review.fingerprint
    assert entry.previous_hash == "0" * 64
    assert len(entry.event_hash) == 64
    assert entry.reusable
    assert journal.verify("owner-a", "claim-42", authorized=True)
    assert journal.latest("owner-a", "claim-42", authorized=True) == entry


def test_two_reviews_extend_one_hash_linked_chain():
    journal = ledger()
    first = journal.append(
        "owner-a", report(), observed_at=10.0,
        expected_sequence=0, authorized=True,
    )
    second_review = report(current=capture("Revised content changes original quote."))
    second = journal.append(
        "owner-a", second_review, observed_at=20.0,
        expected_sequence=1, authorized=True,
    )
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert second.event_hash != first.event_hash
    assert not second.reusable
    assert journal.verify("owner-a", "claim-42", authorized=True)
    assert journal.entries("owner-a", "claim-42", authorized=True) == (
        second, first,
    )


def test_exact_retry_reuses_receipt_not_second_event():
    journal = ledger()
    review = report()
    first = journal.append(
        "owner-a", review, observed_at=100.0, expected_sequence=0,
        authorized=True,
    )
    again = journal.append(
        "owner-a", review, observed_at=100.0, expected_sequence=0,
        authorized=True,
    )
    assert first == again
    assert len(journal.entries("owner-a", "claim-42", authorized=True)) == 1


def test_stale_or_conflicting_replay_rejected():
    journal = ledger()
    review = report()
    journal.append(
        "owner-a", review, observed_at=1.0, expected_sequence=0,
        authorized=True,
    )
    with pytest.raises(RuntimeError, match="stale"):
        journal.append(
            "owner-a", review, observed_at=2.0, expected_sequence=0,
            authorized=True,
        )
    assert journal.verify("owner-a", "claim-42", authorized=True)


def test_unauthorized_reads_writes_and_deletes_fail_closed():
    journal = ledger()
    review = report()
    with pytest.raises(PermissionError):
        journal.append(
            "owner-a", review, observed_at=1.0,
            expected_sequence=0, authorized=False,
        )
    with pytest.raises(PermissionError):
        journal.latest("owner-a", "claim-42", authorized=False)
    with pytest.raises(PermissionError):
        journal.entries("owner-a", "claim-42", authorized=False)
    with pytest.raises(PermissionError):
        journal.verify("owner-a", "claim-42", authorized=False)
    with pytest.raises(PermissionError):
        journal.erase("owner-a", authorized=False)


def test_owners_are_isolated_and_erasure_is_owner_scoped():
    journal = ledger()
    review = report()
    a = journal.append(
        "owner-a", review, observed_at=1, expected_sequence=0,
        authorized=True,
    )
    b = journal.append(
        "owner-b", review, observed_at=1, expected_sequence=0,
        authorized=True,
    )
    assert a.event_hash != b.event_hash
    assert journal.erase("owner-a", authorized=True) == 1
    assert journal.entries("owner-a", "claim-42", authorized=True) == ()
    assert journal.latest("owner-a", "claim-42", authorized=True) is None
    assert journal.verify("owner-a", "claim-42", authorized=True)
    assert journal.latest("owner-b", "claim-42", authorized=True) == b
    assert journal.verify("owner-b", "claim-42", authorized=True)


def test_mutating_event_breaks_verification():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    journal.db.execute("""
        UPDATE crawler_revision_events SET invalidated_readings=99
        WHERE owner='owner-a'
    """)
    journal.db.commit()
    assert not journal.verify("owner-a", "claim-42", authorized=True)


def test_mutating_chain_link_breaks_verification():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    journal.db.execute("""
        UPDATE crawler_revision_events SET previous_hash=?
        WHERE owner='owner-a'
    """, ("b" * 64,))
    journal.db.commit()
    assert not journal.verify("owner-a", "claim-42", authorized=True)


def test_mutating_head_blocks_future_append_and_detection():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    journal.db.execute("""
        UPDATE crawler_revision_events SET event_hash=?
        WHERE owner='owner-a'
    """, ("d" * 64,))
    journal.db.commit()
    assert not journal.verify("owner-a", "claim-42", authorized=True)
    with pytest.raises(RuntimeError, match="tampered"):
        journal.append(
            "owner-a", report(), observed_at=2, expected_sequence=1,
            authorized=True,
        )


def test_deleting_event_with_head_intact_fails_verification():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    journal.db.execute(
        "DELETE FROM crawler_revision_events WHERE owner='owner-a'"
    )
    journal.db.commit()
    assert not journal.verify("owner-a", "claim-42", authorized=True)


def test_owner_journal_capacity_enforced_without_partial_write():
    journal = ledger(max_per_claim=1)
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    with pytest.raises(ValueError, match="capacity"):
        journal.append(
            "owner-a", report(), observed_at=2, expected_sequence=1,
            authorized=True,
        )
    assert journal.verify("owner-a", "claim-42", authorized=True)


def test_invalid_digest_and_inconsistent_invalidation_fail_closed():
    journal = ledger()
    original = report()
    with pytest.raises(ValueError, match="fingerprint"):
        journal.append(
            "owner-a", replace(original, fingerprint="not-a-digest"),
            observed_at=1, expected_sequence=0, authorized=True,
        )
    with pytest.raises(ValueError, match="inconsistent"):
        journal.append(
            "owner-a", replace(original, invalidated_readings=1),
            observed_at=1, expected_sequence=0, authorized=True,
        )


@pytest.mark.parametrize("timestamp", [-1, float("nan"), float("inf"), True])
def test_invalid_timestamps_rejected(timestamp):
    journal = ledger()
    with pytest.raises(ValueError, match="timestamp"):
        journal.append(
            "owner-a", report(), observed_at=timestamp, expected_sequence=0,
            authorized=True,
        )


def test_active_foreign_transaction_rejected_not_hijacked():
    journal = ledger()
    journal.db.execute("BEGIN")
    try:
        with pytest.raises(RuntimeError, match="existing transaction"):
            journal.append(
                "owner-a", report(), observed_at=1, expected_sequence=0,
                authorized=True,
            )
    finally:
        journal.db.rollback()
    assert journal.verify("owner-a", "claim-42", authorized=True)


def test_query_and_integrity_budget_fail_closed():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1, expected_sequence=0,
        authorized=True,
    )
    with pytest.raises(ValueError, match="budget"):
        journal.entries("owner-a", "claim-42", authorized=True, limit=0)
    with pytest.raises(ValueError, match="limit"):
        journal.verify("owner-a", "claim-42", authorized=True, max_events=0)


def test_empty_journal_integrity_is_true_but_unauthorized_is_denied():
    journal = ledger()
    assert journal.verify("unknown-owner", "claim-42", authorized=True)
    assert journal.latest("unknown-owner", "claim-42", authorized=True) is None


def test_forged_stale_fingerprint_rejected_even_with_valid_hex():
    journal = ledger()
    original = report()
    # An attacker changes a revision disposition without recomputing the
    # canonical report digest. A syntactically valid SHA-256 string is not proof.
    forged = replace(original, prior_readings_reusable=False)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        journal.append(
            "owner-a", forged, observed_at=1,
            expected_sequence=0, authorized=True,
        )


def test_modified_nested_reading_disposition_rejected():
    journal = ledger()
    original = report()
    changed_readings = tuple(replace(x, matching_quotes=0) for x in original.readings)
    tampered = replace(original, readings=changed_readings)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        journal.append(
            "owner-a", tampered, observed_at=1,
            expected_sequence=0, authorized=True,
        )


def test_corrupt_persisted_source_list_is_detected_not_raised():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1,
        expected_sequence=0, authorized=True,
    )
    journal.db.execute("""
        UPDATE crawler_revision_events
        SET added_sources='not-json'
        WHERE owner='owner-a'
    """)
    journal.db.commit()
    assert journal.verify("owner-a", "claim-42", authorized=True) is False


def test_corrupt_source_list_preserving_valid_json_is_still_detected():
    journal = ledger()
    journal.append(
        "owner-a", report(), observed_at=1,
        expected_sequence=0, authorized=True,
    )
    journal.db.execute("""
        UPDATE crawler_revision_events
        SET missing_sources='["forged"]'
        WHERE owner='owner-a'
    """)
    journal.db.commit()
    assert journal.verify("owner-a", "claim-42", authorized=True) is False


def test_review_digest_is_deterministic_and_checks_source_mutation():
    from skeleton.ai.webcrawler.dragon_crawl_revision import (
        revision_report_fingerprint,
    )
    review = report()
    assert revision_report_fingerprint(review) == review.fingerprint
    corrupted = replace(
        review,
        sources=(replace(review.sources[0], lineage_changed=True),),
    )
    assert revision_report_fingerprint(corrupted) != review.fingerprint
