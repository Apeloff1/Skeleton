"""Aggregated catalog assurance must revalidate untrusted pages against source."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def two_pages():
    first = batch.audit_catalog_walk_choices(authorized=True, limit=1)
    second = batch.audit_catalog_walk_choices(
        authorized=True, offset=first["next_offset"], limit=1,
        expected_catalog_digest=first["catalog_digest"],
    )
    return [first, second]


def test_merge_revalidates_real_canonical_pages_and_is_deterministic():
    pages = two_pages()
    merged = batch.merge_catalog_walk_audits(pages, authorized=True)
    assert merged == batch.merge_catalog_walk_audits(pages, authorized=True)
    assert merged["pages_verified"] == 2
    assert merged["projects_verified"] == 2
    assert merged["catalog_digest"] == pages[0]["catalog_digest"]
    assert merged["next_offset"] == 2
    assert merged["complete_catalog_coverage"] is False
    assert merged["release_certified"] is False
    assert len(merged["merge_digest"]) == 64


@pytest.mark.parametrize("tamper", [
    lambda pages: pages.reverse(),
    lambda pages: pages.append(deepcopy(pages[0])),
    lambda pages: pages[0].update({"complete_catalog_coverage": True}),
    lambda pages: pages[0].update({"audit_digest": "0" * 64}),
    lambda pages: pages[1].update({"page_offset": 0}),
    lambda pages: pages[1].update({"catalog_digest": "0" * 64}),
    lambda pages: pages[1].update({"genre": "forged"}),
    lambda pages: pages[0]["projects"][0].update({"status": "covered"}),
])
def test_untrusted_merge_page_fails_closed(tamper):
    pages = two_pages()
    tamper(pages)
    with pytest.raises(StudioQuestError):
        batch.merge_catalog_walk_audits(pages, authorized=True)


def test_authorization_precedes_source_replay(monkeypatch):
    monkeypatch.setattr(batch, "audit_catalog_walk_choices",
                        lambda **_: pytest.fail("unauthorized source read"))
    with pytest.raises(PermissionError):
        batch.merge_catalog_walk_audits([{}], authorized=False)


@pytest.mark.parametrize("invalid", [[], [{}] * 5, "bad", [None], [True]])
def test_invalid_merge_shape_fails_closed(invalid):
    with pytest.raises(StudioQuestError):
        batch.merge_catalog_walk_audits(invalid, authorized=True)
