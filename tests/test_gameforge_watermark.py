import pytest

from skeleton.frontier.gameforge_watermark import Watermark


def test_watermark_only_moves_forward():
    watermark = Watermark()
    watermark.observe(4)
    watermark.observe(2)
    assert watermark.value == 4


def test_watermark_rejects_negative_observation():
    with pytest.raises(ValueError):
        Watermark().observe(-1)


def test_watermark_rejects_boolean_values():
    with pytest.raises(ValueError):
        Watermark(True)
    with pytest.raises(ValueError):
        Watermark().observe(True)
