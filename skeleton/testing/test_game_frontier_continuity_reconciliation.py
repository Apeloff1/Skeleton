"""Regression coverage for additive continuity reconciliation.

The original epoch/saga/epic index positions remain stable; continuity is a
separate virtual namespace rather than a destructive replacement for Epic.
"""
from __future__ import annotations

import pytest

from skeleton.forge.game_frontier_studio_authoring import AUTHORING_ACTIONS
from skeleton.forge.game_frontier_studio_continuity_production import (
    CONTINUITY_ACTIONS, CONTINUITIES, describe_continuity, search_continuities,
)
from skeleton.forge.game_frontier_studio_continuity_handbooks import list_books
from skeleton.forge.game_frontier_studio import StudioError


def test_existing_authoring_indices_are_preserved():
    assert len(AUTHORING_ACTIONS) == 50_000_000_000_000
    assert len(CONTINUITY_ACTIONS) == 4_500_000_000_000
    assert len(set(CONTINUITIES)) == 10
    assert AUTHORING_ACTIONS[-1].startswith("epic_")


def test_continuity_index_is_bijective_and_source_backed():
    for index in (0, 1, 9, 10, 450_000, len(CONTINUITY_ACTIONS) - 1):
        operation = CONTINUITY_ACTIONS[index]
        assert operation in CONTINUITY_ACTIONS
        detail = describe_continuity(operation)
        assert detail["operation"] == operation
        assert detail["continuity"] in CONTINUITIES
        assert detail["actual_project_mutation"] is True
    assert "continuity_unregistered" not in CONTINUITY_ACTIONS


def test_continuity_paging_and_filters_are_bounded():
    output = search_continuities(continuity=CONTINUITIES[0], offset=0, limit=3)
    assert output["schema"] == "skeleton.forge.production_recipe_search.v1"
    assert output["total_catalog"] == 4_500_000_000_000
    assert len(output["items"]) == 3
    assert all(item["continuity"] == CONTINUITIES[0] for item in output["items"])
    with pytest.raises(StudioError):
        search_continuities(limit=65)
    with pytest.raises(StudioError):
        search_continuities(continuity="unregistered")


def test_bounded_virtual_handbook_discovery():
    results = list_books(offset=0, limit=2)
    assert results["matched"] > 0
    assert len(results["items"]) == 2
    with pytest.raises(StudioError):
        list_books(limit=65)


def test_all_ten_continuity_motions_mutate_real_source_deterministically():
    from skeleton.forge.game_frontier_studio import StudioProject
    from skeleton.forge.game_frontier_studio_authoring import (
        execute_authoring, project_digest,
    )
    from skeleton.testing.test_game_frontier_studio_production_5000 import (
        original_project, arguments,
    )

    baseline = original_project()
    source = project_digest(baseline)
    resulting_digests = set()
    for treatment in range(10):
        name = CONTINUITY_ACTIONS[treatment]
        params = arguments(name)
        edited = execute_authoring(baseline, name, params)
        replayed = execute_authoring(baseline, name, params)
        assert isinstance(edited, StudioProject)
        assert project_digest(edited) != source
        assert project_digest(edited) == project_digest(replayed)
        assert edited.project_id == baseline.project_id
        assert edited.placements[:len(baseline.placements)] == baseline.placements
        assert edited.native_quests[:len(baseline.native_quests)] == baseline.native_quests
        assert len(edited.environmental_pages) > len(baseline.environmental_pages)
        resulting_digests.add(project_digest(edited))
    assert len(resulting_digests) == 10
    assert project_digest(baseline) == source


def test_real_continuity_transaction_roundtrips_without_changing_original():
    from skeleton.forge.game_frontier_studio_authoring import (
        apply_authoring_batch, project_digest, authored_summary,
    )
    from skeleton.forge.game_frontier_studio_document import (
        authored_document, load_authored_document,
    )
    from skeleton.testing.test_game_frontier_studio_production_5000 import (
        original_project, arguments,
    )

    source = original_project()
    before = project_digest(source)
    operation = CONTINUITY_ACTIONS[3]
    params = arguments(operation)
    result = apply_authoring_batch(source, [
        {"action": operation, "parameters": params},
    ])
    updated = result["project"]
    assert result["receipt"]["actually_changed"] is True
    assert result["receipt"]["persisted"] is False
    assert result["receipt"]["source_sha256"] == before
    assert result["receipt"]["candidate_sha256"] == project_digest(updated)
    assert authored_summary(updated)["continuity_recipe_count"] == 4_500_000_000_000
    assert authored_summary(updated)["catalog_total"] == 50_000_000_000_000
    recovered = load_authored_document(
        authored_document(updated), project_id=source.project_id,
    )
    assert project_digest(recovered) == project_digest(updated)
    assert project_digest(source) == before

    # A late invalid continuation must not commit any earlier candidate edit.
    with pytest.raises(StudioError):
        apply_authoring_batch(source, [
            {"action": operation, "parameters": params},
            {"action": operation, "parameters": {**params, "wall": params["floor"]}},
        ])
    assert project_digest(source) == before


def test_continuity_book_receipts_and_ranked_rendered_manuscripts():
    from hashlib import sha256
    from skeleton.forge.game_frontier_studio_continuity_handbooks import (
        BOOK_COUNT, identity, number, receipt, rank_variants,
    )

    assert BOOK_COUNT == 900_000_000
    for index in (0, 9, 10, 123_456, BOOK_COUNT - 1):
        exact = identity(index)
        assert number(*exact) == index
    item = receipt(*identity(0))
    assert item["schema"] == "skeleton.forge.continuity_handbook.v1"
    assert item["quality_score"] >= 75
    assert item["covered_commands"] == 5000
    assert sha256(item["markdown"].encode("utf8")).hexdigest() == item["content_sha256"]
    assert item["words"] > 100
    context = identity(0)[:-1]
    by_quality = rank_variants(*context, sort="quality")
    by_length = rank_variants(*context, sort="length")
    assert by_quality["compared"] == by_length["compared"] == 10
    assert len(by_quality["items"]) == len(by_length["items"]) == 10
    assert by_quality["items"] == sorted(
        by_quality["items"],
        key=lambda row: (-row["quality_score"], -row["words"], row["continuity"]),
    )
    assert by_length["items"] == sorted(
        by_length["items"],
        key=lambda row: (-row["words"], -row["quality_score"], row["continuity"]),
    )
    assert all(len(row["content_sha256"]) == 64 for row in by_quality["items"])


def test_exact_rank_unrank_boundaries_and_filtered_pagination():
    from skeleton.forge.game_frontier_studio_continuity_production import parent_action
    from skeleton.forge.game_frontier_studio_epoch_production import EPOCH_ACTIONS

    for index in (0, 1, 9, 10, 98, 1_000_001, len(CONTINUITY_ACTIONS) - 1):
        name = CONTINUITY_ACTIONS[index]
        original, axis = parent_action(name)
        assert original == EPOCH_ACTIONS[index // 10]
        assert name == CONTINUITY_ACTIONS[index]
        assert CONTINUITIES[axis] == CONTINUITIES[index % 10]
    for start in (0, 9, 999, len(CONTINUITY_ACTIONS) - 3):
        page = search_continuities(offset=start, limit=3)
        assert [item["operation"] for item in page["items"]] == list(
            CONTINUITY_ACTIONS[start:start + 3]
        )
    picked = search_continuities(
        domain="realm", continuity=CONTINUITIES[1], limit=4,
    )
    assert picked["matched"] == 450 * 10**8
    assert all(row["continuity"] == CONTINUITIES[1] for row in picked["items"])
    for invalid in (True, 1.0, "0", -1):
        with pytest.raises(StudioError):
            search_continuities(offset=invalid)
    with pytest.raises(StudioError):
        search_continuities(limit=0)
    with pytest.raises(StudioError):
        search_continuities(domain="../../untrusted")
