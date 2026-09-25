"""The verifier does not score a different script when the weak one is missing."""

import pytest

from skeleton.forge.verify_loop import _primary_script, forge_verify_until_green


def test_the_first_script_is_not_a_stand_in() -> None:
    files = {"a.gd": "extends Node\n", "b.gd": "extends Node\n"}
    assert _primary_script(files, "") == ("", "")
    assert _primary_script(files, "missing.gd") == ("", "")
    assert _primary_script(files, "b.gd") == ("b.gd", "extends Node\n")
    with pytest.raises(ValueError):
        forge_verify_until_green({}, request="build the level")
    with pytest.raises(ValueError):
        forge_verify_until_green(files, request="")
    with pytest.raises(ValueError):
        forge_verify_until_green(files, request="build the level", max_rounds=True)
