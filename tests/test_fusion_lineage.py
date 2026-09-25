"""Fusion must expose exact contribution lineage without mutating inputs."""

import pytest

from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult


def _hit(fragment_id: str, plane: str, score: float = 1.0) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=f"{fragment_id}:{plane}",
        score=score,
        plane=plane,
        metadata={"owner": plane},
    )


def test_rrf_duplicate_fragment_records_all_plane_contributions() -> None:
    rag = _hit("shared", "rag", 0.2)
    kag = _hit("shared", "kag", 0.9)

    fused = Fuser(k=60).fuse({"rag": [rag], "kag": [kag]}, top_k=1)[0]

    assert fused.fragment_id == "shared"
    assert fused.metadata["fusion_planes"] == ("kag", "rag")
    assert set(fused.metadata["fusion_contributions"]) == {"rag", "kag"}
    assert fused.score == pytest.approx(2.0 / 61.0)
    assert fused.metadata["fusion_score"] == pytest.approx(fused.score)
    assert "fusion_planes" not in rag.metadata
    assert "fusion_planes" not in kag.metadata


def test_weighted_rrf_changes_ranking_and_keeps_exact_contributions() -> None:
    fuser = Fuser(k=10)
    results = {
        "rag": [_hit("rag-only", "rag")],
        "kag": [_hit("kag-only", "kag")],
    }

    fused = fuser.weighted_rrf(
        results,
        {"rag": 0.1, "kag": 2.0},
        top_k=2,
    )

    assert [row.fragment_id for row in fused] == ["kag-only", "rag-only"]
    assert fused[0].metadata["fusion_contributions"]["kag"] == pytest.approx(2 / 11)


def test_confidence_fusion_implements_noisy_or() -> None:
    fuser = Fuser(strategy=FusionStrategy.CONFIDENCE)
    fused = fuser.fuse(
        {
            "rag": [_hit("shared", "rag", 0.5)],
            "kag": [_hit("shared", "kag", 0.5)],
        },
        top_k=1,
    )
    assert fused[0].score == pytest.approx(0.75)
    assert fused[0].metadata["fusion_planes"] == ("kag", "rag")


def test_confidence_fusion_rejects_non_probability_scores() -> None:
    fuser = Fuser(strategy=FusionStrategy.CONFIDENCE)
    with pytest.raises(ValueError, match="in .0, 1."):
        fuser.fuse({"rag": [_hit("bad", "rag", 1.2)]})
