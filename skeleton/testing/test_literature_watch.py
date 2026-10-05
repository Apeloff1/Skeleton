from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import LiteratureItem, LiteratureWatch
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    LiteratureSourceAdapter,
    ResearchEvaluationAssuranceError,
    triage_literature,
)


A = "a" * 64


def adapter(tier: str = "primary") -> LiteratureSourceAdapter:
    return LiteratureSourceAdapter(
        "arxiv",
        "preprint-feed",
        tier,
        "rss",
        ("research-review",),
    )


def item(*, retracted: bool = False) -> LiteratureItem:
    return LiteratureItem("paper-1", "v1", "Useful paper", A, retracted)


def test_primary_topic_match_binds_urgent_item_to_backlog() -> None:
    evidence = triage_literature(
        LiteratureWatch(),
        adapter(),
        item(),
        topic_match=True,
        license_class="research-review",
        backlog_ref="RESEARCH-123",
    )
    assert evidence.priority == "urgent"
    assert evidence.backlog_ref == "RESEARCH-123"
    assert evidence.production_authority is False


def test_retracted_or_unlicensed_item_cannot_enter_review_queue() -> None:
    retracted = triage_literature(
        LiteratureWatch(),
        adapter(),
        item(retracted=True),
        topic_match=True,
        license_class="research-review",
    )
    assert retracted.priority == "ignore"
    assert retracted.reason_codes == ("retracted",)

    blocked = triage_literature(
        LiteratureWatch(),
        adapter(),
        item(),
        topic_match=True,
        license_class="forbidden",
    )
    assert blocked.priority == "ignore"
    assert blocked.reason_codes == ("license-not-approved",)


def test_reviewable_item_requires_backlog_binding() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError):
        triage_literature(
            LiteratureWatch(),
            adapter("curated"),
            item(),
            topic_match=True,
            license_class="research-review",
        )
