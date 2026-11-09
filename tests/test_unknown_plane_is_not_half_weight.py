"""An unknown plane is not fused at half weight, and a partial weight map is incomplete."""

import pytest

from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult


def _hit(fragment_id: str, plane: str) -> ScoredResult:
    return ScoredResult(fragment_id=fragment_id, content=fragment_id, score=1.0, plane=plane)


def test_unknown_plane_and_partial_weights_raise() -> None:
    fuser = Fuser(strategy=FusionStrategy.WEIGHTED)
    with pytest.raises(ValueError):
        fuser.fuse({"index": [_hit("doc", "index")]})
    with pytest.raises(ValueError):
        fuser.weighted_rrf({"rag": [_hit("doc", "rag")], "kag": [_hit("other", "kag")]}, {"rag": 1.0})
    fused = fuser.fuse({"rag": [_hit("doc", "rag")]})
    assert fused[0].fragment_id == "doc"
