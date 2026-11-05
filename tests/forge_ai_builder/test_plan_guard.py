import pytest

from skeleton.forge.ai_builder import guard_proposal, normalize_prompt, parse_model_plan
from skeleton.forge.ai_builder.plan_schema import PlanParseError
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS, compile_brief

SPEC = compile_brief(GOLDEN_BRIEFS[0]["brief"])


def test_locked_fields_ignored_and_reported():
    spec, v = guard_proposal(SPEC, {"genre": "platformer", "engine": "unity", "title": "Ash"})
    assert spec["genre"] == SPEC["genre"] and spec["engine"] == "godot4" and spec["title"] == "Ash"
    assert set(v) == {"locked:genre", "locked:engine"}


def test_spec_id_resealed_like_compiler():
    same, v = guard_proposal(SPEC, {})
    assert same == SPEC and v == ()


def test_systems_only_subset():
    spec, v = guard_proposal(SPEC, {"systems": ["combat", "levels"]})
    assert spec["systems"] == ["combat", "levels"] and not v
    spec, v = guard_proposal(SPEC, {"systems": ["blockchain"]})
    assert spec["systems"] == SPEC["systems"] and v == ("unknown:systems",)
    _, v = guard_proposal(SPEC, {"systems": []})
    assert v == ("invalid:systems",)


def test_text_bounds():
    _, v = guard_proposal(SPEC, {"title": "x" * 81, "fantasy": 3})
    assert set(v) == {"too_long:title", "invalid:fantasy"}


def test_parse_variants():
    assert parse_model_plan('```json\n{"title": "A"}\n```') == {"title": "A"}
    assert parse_model_plan({"schema": "skeleton.forge.ai_builder.plan_proposal.v1", "title": "B"}) == {"title": "B"}
    for bad in ("[1]", "nope", {"schema": "other"}, None):
        with pytest.raises(PlanParseError):
            parse_model_plan(bad)


def test_normalize_prompt():
    assert normalize_prompt("  a\x00 small\u200b\n\nplatformer ") == "a small platformer"
    assert len(normalize_prompt("x" * 9000)) == 4000
    for bad in ("", " \n", 5):
        with pytest.raises(ValueError):
            normalize_prompt(bad)
