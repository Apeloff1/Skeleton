from __future__ import annotations

import pytest

from skeleton.frontier.reputation import (
    ReputationLevel,
    apply_reputation_change,
    calculate_spillover,
    current_benefits,
    faction_from_record,
    next_reputation_level,
    reputation_level,
    standing_summary,
)


def _faction():
    return faction_from_record(
        {
            "id": "fishermen_guild",
            "name": "Fishermen's Guild",
            "benefits": {
                "friendly": ["guild_shop_access", "fishing_tips"],
                "honored": ["guild_quests", "discount_10"],
                "revered": ["advanced_training", "discount_20"],
                "exalted": ["master_techniques", "discount_30"],
            },
            "allies": ["merchants", "port_authority"],
            "enemies": ["pirates"],
            "leader": "guild_master_thornwood",
        }
    )


def test_faction_adapter_preserves_relationships_benefits_and_metadata():
    faction = _faction()

    assert faction.id == "fishermen_guild"
    assert faction.allies == ("merchants", "port_authority")
    assert faction.enemies == ("pirates",)
    assert faction.benefits["friendly"] == ("guild_shop_access", "fishing_tips")
    assert faction.metadata["leader"] == "guild_master_thornwood"


def test_faction_adapter_deduplicates_relationships_and_rejects_contradictions():
    deduplicated = faction_from_record(
        {
            "id": "guild",
            "name": "Guild",
            "allies": ["merchants", "merchants", "PORT_AUTHORITY"],
            "enemies": ["pirates", "pirates"],
        }
    )
    assert deduplicated.allies == ("merchants", "port_authority")
    assert deduplicated.enemies == ("pirates",)

    with pytest.raises(ValueError, match="allied with or hostile to itself"):
        faction_from_record(
            {"id": "guild", "name": "Guild", "allies": ["guild"]}
        )

    with pytest.raises(ValueError, match="allies and enemies overlap"):
        faction_from_record(
            {
                "id": "guild",
                "name": "Guild",
                "allies": ["merchants"],
                "enemies": ["MERCHANTS"],
            }
        )


def test_reputation_threshold_edges_are_unambiguous():
    assert reputation_level(-1001).name == "Hated"
    assert reputation_level(-500).name == "Hostile"
    assert reputation_level(-200).name == "Unfriendly"
    assert reputation_level(-1).name == "Unfriendly"
    assert reputation_level(0).name == "Neutral"
    assert reputation_level(499).name == "Neutral"
    assert reputation_level(500).name == "Friendly"
    assert reputation_level(3000).name == "Honored"
    assert reputation_level(9000).name == "Revered"
    assert reputation_level(21000).name == "Exalted"
    assert reputation_level(2_000_000).name == "Exalted"


def test_custom_reputation_levels_require_unique_monotonic_identity():
    duplicate_rank = (
        ReputationLevel(min_rep=0, rank=0, name="Neutral"),
        ReputationLevel(min_rep=500, rank=0, name="Friendly"),
    )
    with pytest.raises(ValueError, match="ranks must be unique"):
        reputation_level(500, levels=duplicate_rank)

    reversed_rank = (
        ReputationLevel(min_rep=0, rank=1, name="Neutral"),
        ReputationLevel(min_rep=500, rank=0, name="Friendly"),
    )
    with pytest.raises(ValueError, match="ranks must increase"):
        reputation_level(500, levels=reversed_rank)


def test_next_level_reports_threshold_and_remaining_reputation():
    assert next_reputation_level(499) == {
        "name": "Friendly",
        "required": 500,
        "needed": 1,
    }
    assert next_reputation_level(3000) == {
        "name": "Revered",
        "required": 9000,
        "needed": 6000,
    }
    assert next_reputation_level(21000) is None


def test_benefits_accumulate_through_current_positive_tier():
    faction = _faction()

    assert current_benefits(faction, "neutral") == ()
    assert current_benefits(faction, "friendly") == (
        "guild_shop_access",
        "fishing_tips",
    )
    assert current_benefits(faction, "revered") == (
        "guild_shop_access",
        "fishing_tips",
        "guild_quests",
        "discount_10",
        "advanced_training",
        "discount_20",
    )


def test_positive_spillover_rewards_allies_and_penalizes_enemies():
    deltas = calculate_spillover(_faction(), 100)

    assert [(delta.faction_id, delta.amount, delta.effect_type) for delta in deltas] == [
        ("merchants", 25, "ally_bonus"),
        ("port_authority", 25, "ally_bonus"),
        ("pirates", -50, "enemy_penalty"),
    ]


def test_negative_spillover_only_affects_allies_with_source_sympathy_rule():
    deltas = calculate_spillover(_faction(), -100)

    assert [(delta.faction_id, delta.amount, delta.effect_type) for delta in deltas] == [
        ("merchants", -25, "ally_sympathy"),
        ("port_authority", -25, "ally_sympathy"),
    ]


def test_reputation_change_reports_level_transition_benefits_and_spillover():
    result = apply_reputation_change(_faction(), 490, 20)

    assert result.old_reputation == 490
    assert result.new_reputation == 510
    assert result.old_level.name == "Neutral"
    assert result.new_level.name == "Friendly"
    assert result.level_changed
    assert result.new_benefits == ("guild_shop_access", "fishing_tips")
    assert result.spillover[0].amount == 5


def test_standing_summary_counts_untracked_factions_as_neutral():
    summary = standing_summary(
        {
            "fishermen_guild": 500,
            "pirates": -600,
            "merchants": 4000,
        },
        ["fishermen_guild", "pirates", "merchants", "mystics"],
    )

    assert summary["total_factions"] == 4
    assert summary["standings"]["friendly"] == 1
    assert summary["standings"]["hated"] == 1
    assert summary["standings"]["honored"] == 1
    assert summary["standings"]["neutral"] == 1
    assert summary["best_standing"] == {
        "faction": "merchants",
        "reputation": 4000,
        "level": "Honored",
    }
    assert summary["worst_standing"] == {
        "faction": "pirates",
        "reputation": -600,
        "level": "Hated",
    }


def test_standing_summary_normalizes_ids_and_rejects_ambiguous_catalogs():
    summary = standing_summary({"PIRATES": -600}, ["pirates", "mystics"])
    assert summary["standings"]["hated"] == 1
    assert summary["standings"]["neutral"] == 1

    with pytest.raises(ValueError, match="duplicate faction id"):
        standing_summary({}, ["pirates", "PIRATES"])


def test_standing_summary_rejects_unknown_tracked_factions():
    with pytest.raises(KeyError, match="unknown reputation factions"):
        standing_summary({"unknown": 10}, ["known"])
