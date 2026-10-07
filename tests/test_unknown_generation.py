"""An unknown machine is not called modern."""

import pytest

from skeleton.forge.hardware import detect_generation, get_generation


def test_garbage_is_not_a_modern_console() -> None:
    with pytest.raises(ValueError):
        get_generation("garbage")
    with pytest.raises(ValueError):
        get_generation(True)
    assert get_generation(None)["key"] == "modern"
    assert get_generation("NES")["key"] == "8bit"
    assert get_generation("PS5")["key"] == "modern"
    with pytest.raises(ValueError):
        detect_generation("a quiet afternoon with no console")
    era, scores = detect_generation("a nes chiptune on famicom")
    assert era == "8bit"
    assert scores["8bit"] >= 2
