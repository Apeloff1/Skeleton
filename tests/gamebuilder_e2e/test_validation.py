"""Input validation on the builder entry point."""
from __future__ import annotations

import pytest

from skeleton.forge.game_builder import build_playable_game, coerce_brief


@pytest.mark.parametrize("brief", ["", "   ", "\n\t"])
def test_blank_brief_rejected(brief):
    with pytest.raises(ValueError, match="brief is required"):
        build_playable_game(brief, playtest_mode="off")


@pytest.mark.parametrize("deadline", [-1, -0.5, True, "10"])
def test_bad_deadline_rejected(deadline):
    with pytest.raises(ValueError, match="deadline_s"):
        build_playable_game("a platformer", playtest_mode="off", deadline_s=deadline)


def test_bad_repair_mode_rejected():
    with pytest.raises(ValueError, match="repair_mode"):
        build_playable_game("a platformer", playtest_mode="off", repair_mode="yolo")


@pytest.mark.parametrize("field", ["actor_id", "tenant_id", "execution_id", "project_id"])
@pytest.mark.parametrize("value", ["has space", "-leading", "x" * 129, "a/b"])
def test_bad_identifiers_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        build_playable_game("a platformer", playtest_mode="off", **{field: value})


def test_identifiers_echoed():
    result = build_playable_game(
        "a platformer", playtest_mode="off", actor_id="actor-1", tenant_id="t.1",
        execution_id="exec:1", project_id="proj_1",
    )
    assert (result["actor_id"], result["tenant_id"], result["execution_id"], result["project_id"]) == (
        "actor-1", "t.1", "exec:1", "proj_1",
    )


def test_zero_deadline_halts_without_building():
    result = build_playable_game("a platformer", playtest_mode="off", deadline_s=0)
    assert result["ok"] is False
    assert not result.get("files")


class TestStructuredBrief:
    def test_minimal(self):
        structured, text = coerce_brief({"title": "Fox Run"})
        assert structured["title"] == "Fox Run" and text == "Fox Run"

    def test_full_text(self):
        _, text = coerce_brief({"title": "T", "summary": "S", "genre": "platformer", "constraints": ["a", "b"]})
        assert text == "T S Genre: platformer. Constraints: a; b"

    @pytest.mark.parametrize(
        "brief,match",
        [
            ({"title": "x", "actor_id": "y"}, "unknown brief fields"),
            ({"title": "x", "schema_version": "v0"}, "schema_version"),
            ({"title": "  "}, "title is required"),
            ({}, "title is required"),
            ({"title": "x", "summary": 3}, "summary"),
            ({"title": "x", "genre": []}, "genre"),
            ({"title": "x", "constraints": "a"}, "constraints"),
            ({"title": "x", "constraints": [1]}, "constraints"),
        ],
    )
    def test_rejections(self, brief, match):
        with pytest.raises(ValueError, match=match):
            coerce_brief(brief)

    def test_non_mapping_rejected(self):
        with pytest.raises(ValueError):
            coerce_brief(42)  # type: ignore[arg-type]

    def test_structured_build_records_brief(self):
        result = build_playable_game(
            {"title": "Ledge Fox", "genre": "platformer", "constraints": ["one level"]}, playtest_mode="off",
        )
        assert result["ok"] is True
        assert result["structured_brief"]["title"] == "Ledge Fox"
        assert result["spec"]["genre"] == "platformer"
