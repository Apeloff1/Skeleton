"""A system id is a string, and a quality pass is not a missing key."""

from skeleton.forge.forge_quality import evaluate
from skeleton.forge.validators import BlueprintValidator, FieldRule, validate_with_quality


def test_a_string_dependency_is_not_split_into_letters() -> None:
    verdict = BlueprintValidator().validate({
        "name": "demo",
        "version": "1",
        "systems": [{"id": "core", "depends_on": "core"}],
    })
    assert verdict.valid is False
    assert any(item.rule == "type" for item in verdict.violations)
    assert not any(item.detail.startswith("unknown dependency 'c'") for item in verdict.violations)

    crashed = BlueprintValidator().validate({
        "name": "demo",
        "version": "1",
        "systems": ["core", {"id": True}],
    })
    assert crashed.valid is False
    ranged = BlueprintValidator([FieldRule("version", "range", (0, 2))]).validate({
        "name": "demo",
        "version": True,
        "systems": [{"id": "core", "description": "ready"}],
    })
    assert any(item.rule == "range" for item in ranged.violations)


def test_quality_ok_must_be_one_not_a_missing_passed_flag() -> None:
    blueprint = {
        "name": "demo",
        "version": "1",
        "title": "demo",
        "summary": "a playable demo",
        "content": "the demo body",
        "files": {f"file{i}.gd": "extends Node\n" for i in range(10)},
        "systems": [{"id": "core", "description": "ready"}],
    }
    assert evaluate(blueprint)["ok"] == 1
    assert evaluate({"title": True, "summary": True, "content": True, "files": True})["ok"] == 0
    assert validate_with_quality(blueprint)["valid"] is True
