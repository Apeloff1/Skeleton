"""Regression tests for biotope catch counter ownership."""

from skeleton.frontier.biotope_achievement_adapters import (
    empty_biotope_catch_evidence,
    record_biotope_catch,
)


def test_derived_family_tokens_do_not_double_count_canonical_dimensions():
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="lake_freshwater_common_trout",
        biotope_id="lake",
        stage_id="freshwater",
        size=42,
        rarity="common",
    )

    assert evidence.counts["lake_catches"] == 1
    assert evidence.counts["freshwater_catches"] == 1
    assert evidence.counts["common_catches"] == 1
    assert evidence.counts["trout_catches"] == 1
    assert evidence.counts["freshwater_common"] == 1
    assert evidence.counts["lake_common"] == 1


def test_explicit_family_tokens_cannot_reincrement_canonical_dimensions():
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="trout",
        biotope_id="lake",
        stage_id="freshwater",
        size=42,
        rarity="common",
        family_tokens=("lake", "freshwater", "common", "trout", "trout"),
    )

    assert evidence.counts["lake_catches"] == 1
    assert evidence.counts["freshwater_catches"] == 1
    assert evidence.counts["common_catches"] == 1
    assert evidence.counts["trout_catches"] == 1


def test_canonical_dimensions_with_the_same_token_emit_each_counter_once():
    evidence = record_biotope_catch(
        empty_biotope_catch_evidence(),
        fish_id="lake",
        biotope_id="lake",
        stage_id="lake",
        size=42,
        rarity="lake",
        family_tokens=("lake",),
    )

    assert evidence.counts["lake_catches"] == 1
    assert evidence.counts["lake_lake"] == 1
