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


def test_rgb555_roundtrip_quantization_bounded():
    for r,g,b in ((0,0,0),(255,255,255),(17,127,233)):
        decoded=decode_rgb555(encode_rgb555((r,g,b)))
        assert all(abs(a-b)<=5 for a,b in zip((r,g,b),decoded))
    with pytest.raises(PaletteError):
        decode_rgb555(0x8000)


def test_rgb565_hardware_packing():
    assert encode_rgb565((255,0,0)) == 0xf800
    assert encode_rgb565((0,255,0)) == 0x07e0
    assert encode_rgb565((0,0,255)) == 0x001f
    with pytest.raises(PaletteError):
        encode_rgb565((256,0,0))


def test_rgb565_boundaries_and_roundtrip():
    assert decode_rgb565(0xffff)==(255,255,255)
    for c in ((10,20,30),(127,128,129),(255,0,255)):
        assert max(abs(a-b) for a,b in zip(c,decode_rgb565(encode_rgb565(c))))<=5
    with pytest.raises(PaletteError):
        decode_rgb565(-1)


def test_rgb332_pack_three_three_two_layout():
    assert encode_rgb332((255,0,0))==0xe0
    assert encode_rgb332((0,255,0))==0x1c
    assert encode_rgb332((0,0,255))==0x03
    with pytest.raises(PaletteError):
        encode_rgb332((1,2))


def test_rgb332_roundtrip_and_component_range():
    assert decode_rgb332(255)==(255,255,255)
    for c in ((16,39,103),(200,211,222)):
        got=decode_rgb332(encode_rgb332(c))
        assert all(0<=v<=255 for v in got)
        assert max(abs(a-b) for a,b in zip(c,got))<=43
    with pytest.raises(PaletteError):
        decode_rgb332(True)


def test_palette_nearest_is_weighted_and_first_tie_wins():
    assert nearest_palette_index((3,4,5), ((0,0,0),(255,255,255)))==0
    assert nearest_palette_index((255,250,255), ((0,0,0),(255,255,255)))==1
    assert nearest_palette_index((20,20,20), ((20,20,20),(20,20,20)))==0
    with pytest.raises(PaletteError):
        nearest_palette_index((0,0,0), ())

