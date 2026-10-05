import pytest

from skeleton.frontier.npc_profiles import get_profile, infer_archetype


def test_profiles_are_structured_and_immutable():
    profile = get_profile(" Mage ")
    assert profile.archetype == "mage"
    assert profile.stats["intelligence"] == 18
    assert "spellcasting" in profile.skills


def test_description_inference_uses_source_pipeline_aliases():
    assert infer_archetype("A wise old wizard researching artifacts") == "mage"
    assert infer_archetype("The village shopkeeper") == "merchant"
    assert infer_archetype("An unknown citizen") is None


def test_unknown_profile_fails_closed():
    with pytest.raises(ValueError):
        get_profile("unknown")
