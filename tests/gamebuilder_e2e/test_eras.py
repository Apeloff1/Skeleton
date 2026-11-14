"""Each era profile drives a full, proven build."""
from __future__ import annotations

import pytest

from tests.gamebuilder_e2e.conftest import ERAS, GENRES, build, golden


@pytest.mark.parametrize("era", ERAS)
@pytest.mark.parametrize("genre_id", GENRES)
def test_era_genre_matrix_builds(era, genre_id):
    result = build(golden(genre_id), era=era)
    assert result["ok"] is True, result.get("error")
    assert result["pipeline"]["era"] == era
    assert result["pipeline"]["sim_passed"] is True
    assert result["core_loop"]["passed"] is True
    assert "project.godot" in result["files"]


@pytest.mark.parametrize("era", ERAS)
def test_era_does_not_change_genre(era):
    assert build(golden("platformer"), era=era)["spec"]["genre"] == "platformer"
