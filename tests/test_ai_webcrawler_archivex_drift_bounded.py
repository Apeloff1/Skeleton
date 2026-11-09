"""Adversarial bounds and correctness tests for ArchiveX source drift."""
import sqlite3
from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_signals import (
    ArchiveDriftPolicy, ArchiveSignalKind, compare_snapshots,
)


def snapshots(first, second):
    archive = ArchiveX(sqlite3.connect(":memory:"))
    url = "https://research.example.org/article"
    a = archive.capture(
        "alice", source_url=url, body=first.encode(), observed_at=100,
        now=100, license_note="authorized", authorized=True,
    )
    b = archive.capture(
        "alice", source_url=url, body=second.encode(), observed_at=200,
        now=200, license_note="authorized", authorized=True,
    )
    return (a, first.encode()), (b, second.encode())


def test_exact_text_unchanged():
    first, second = snapshots("abc", "abc")
    result = compare_snapshots(first, second)
    assert result.kind is ArchiveSignalKind.UNCHANGED
    assert result.similarity == 1


def test_one_character_revision_never_marked_unchanged():
    first, second = snapshots("a" * 10000, "a" * 9999 + "b")
    result = compare_snapshots(first, second)
    assert result.kind is not ArchiveSignalKind.UNCHANGED


def test_large_repetitive_document_is_bounded():
    first, second = snapshots("a" * 180000, "b" * 180000)
    result = compare_snapshots(
        first, second,
        policy=ArchiveDriftPolicy(max_comparison_units=64),
    )
    assert result.kind is ArchiveSignalKind.REVISED
    assert result.similarity < 0.01


def test_added_text_detected():
    first, second = snapshots("start", "start with extra details")
    result = compare_snapshots(first, second)
    assert result.kind in (ArchiveSignalKind.EXPANDED, ArchiveSignalKind.REVISED)


def test_first_seen():
    _, second = snapshots("before", "after")
    result = compare_snapshots(None, second)
    assert result.kind is ArchiveSignalKind.FIRST_SEEN


def test_unrelated_sources_fail():
    first, second = snapshots("before", "after")
    from dataclasses import replace
    altered = (replace(second[0], source_url="https://other.example.org"), second[1])
    import pytest
    with pytest.raises(ValueError, match="unrelated"):
        compare_snapshots(first, altered)


def test_invalid_complexity_budget():
    first, second = snapshots("before", "after")
    import pytest
    with pytest.raises(ValueError, match="complexity"):
        compare_snapshots(
            first, second,
            policy=ArchiveDriftPolicy(max_comparison_units=5),
        )
