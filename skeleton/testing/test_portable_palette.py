"""Palette adaptation regression: native bit layouts, reproducibility and bounds."""
import pytest
from skeleton.ai.game_builder.portable_kernels.palette import (
    PaletteError, encode_rgb555, decode_rgb555, encode_rgb565, decode_rgb565,
    encode_rgb332, decode_rgb332, nearest_palette_index, index_image,
    ordered_luma_dither, contrast_ratio,
)


def test_rgb555_packs_each_channel_into_5_bits():
    assert encode_rgb555((255,0,0)) == 0x001f
    assert encode_rgb555((0,255,0)) == 0x03e0
    assert encode_rgb555((0,0,255)) == 0x7c00
    with pytest.raises(PaletteError):
        encode_rgb555((True,0,0))

