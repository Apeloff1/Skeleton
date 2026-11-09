"""An unknown era is not silently renamed extraction_now."""

import pytest

from skeleton.forge.eras import blend_eras, compile_era, era_pack, primary_dps


def test_an_unknown_era_is_rejected_and_an_alias_is_not() -> None:
    with pytest.raises(ValueError):
        era_pack("not-a-real-era")
    with pytest.raises(ValueError):
        era_pack("")
    aliased = era_pack("extraction")
    assert aliased["era"] == "extraction_now"
    soul = compile_era("soulslike")
    assert soul["era"] == "soulslike"
    assert soul["player"]["speed"] == 155.0
    assert soul["primary_dps"] > 0
    with pytest.raises(ValueError):
        primary_dps({"player": {"speed": 0}})
    with pytest.raises(ValueError):
        primary_dps({"player": {"speed": True}})
    with pytest.raises(ValueError):
        blend_eras("soulslike", "extraction_now", 2)
