"""Proof that foundation retrieval ranks authored causal laws, not skins."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_foundation_discovery import (
    search_foundations,
)
from skeleton.game.generation.original_foundation_compiler import (
    FoundationError,
)
from skeleton.game.generation.original_foundation_cli import main


def test_unfiltered_diversity_prevents_single_foundation_family_flood() -> None:
    selected = search_foundations("", limit=40)
    assert len(selected) == 40
    pairs = {(x.foundation.domain, x.foundation.regime.operator) for x in selected}
    assert len(pairs) == 40
    assert all(x.match_score == 0 for x in selected)


def test_exact_operator_domain_and_ending_filters() -> None:
    hits = search_foundations(
        "", domain="ecosphere", operator="veto",
        ending="unwinnable", limit=100, diverse=False,
    )
    assert hits
    assert all(x.foundation.domain == "ecosphere"
               and x.foundation.regime.operator == "veto"
               and x.foundation.ending_policy == "unwinnable"
               for x in hits)


def test_search_uses_causal_words_not_graphics_labels() -> None:
    hits = search_foundations("habitat", limit=20)
    assert hits
    assert all("habitat" in " ".join((
        x.foundation.root.invariant, x.foundation.regime.invariant,
        x.foundation.coupling, x.foundation.player_lever,
        x.foundation.failure_pressure, x.foundation.root.title,
        x.foundation.regime.title,
        x.foundation.domain, x.foundation.regime.operator,
    )).casefold() for x in hits)
    assert all(x.match_score > 0 for x in hits)
    assert not search_foundations("definitelynonexistentworldword123", limit=5)


def test_search_is_deterministic_and_provenance_preserving() -> None:
    first = search_foundations("consent", limit=8)
    second = search_foundations("consent", limit=8)
    assert first == second
    assert all(x.foundation.provenance == "authored-causal-composition"
               for x in first)
    assert all("consent" in x.matched_tokens for x in first)
    assert all(x.source_fields for x in first)


def test_ranking_supports_undiversified_discipline_deep_dives() -> None:
    a = search_foundations("memory", domain="memory",
                           limit=20, diverse=False)
    b = search_foundations("memory", domain="memory",
                           limit=20, diverse=True)
    assert a and b
    assert a[0].match_score >= a[-1].match_score
    assert all(x.foundation.domain == "memory" for x in (*a, *b))
    assert len({x.foundation.regime.operator for x in b}) > 1


@pytest.mark.parametrize("filters", [
    {"domain": "nonexistent"},
    {"operator": "infinite-generator"},
    {"ending": "always-victory"},
    {"limit": 0}, {"limit": 101},
    {"limit": True}, {"diverse": 0},
])
def test_illegal_filter_configuration_rejected(filters) -> None:
    with pytest.raises(FoundationError):
        search_foundations("world", **filters)


def test_discovery_terminal_supports_rich_mechanical_search(capsys) -> None:
    assert main([
        "--find", "care", "--limit", "8",
        "--operator", "fork",
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["query"] == "care"
    assert data["count"] > 0
    assert data["count"] <= 8
    assert all(x["operator"] == "fork" for x in data["matches"])
    assert "not game quality" in data["rank_label"]


def test_query_and_direct_index_are_exclusive(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["--find", "water", "--index", "1"])
