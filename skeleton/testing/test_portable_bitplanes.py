"""Native hardware tile-codec regression suite: real bit layouts and strict bounds."""
import pytest
from skeleton.ai.game_builder.portable_kernels.bitplanes import (
    encode_gb_2bpp, decode_gb_2bpp, encode_nes_2bpp, decode_nes_2bpp,
    encode_snes_4bpp, decode_snes_4bpp, encode_sms_4bpp, decode_sms_4bpp,
    encode_genesis_4bpp, decode_genesis_4bpp, PortableCodecError,
)


def test_encode_gb_2bpp_reference_and_bounds():
    row = (1, 2, 3, 0, 0, 0, 0, 0)
    assert encode_gb_2bpp((row,) * 8) == bytes([0xA0, 0x60] * 8)
    with pytest.raises(PortableCodecError):
        encode_gb_2bpp(((4,) * 8,) * 8)


def test_decode_gb_2bpp_roundtrip_and_length_rejection():
    tile = tuple(tuple((x+y) % 4 for x in range(8)) for y in range(8))
    assert decode_gb_2bpp(encode_gb_2bpp(tile)) == tile
    for blob in (b"", b"\x00"*15, b"\x00"*17):
        with pytest.raises(PortableCodecError):
            decode_gb_2bpp(blob)


def test_encode_nes_2bpp_matches_chr_plane_order():
    row = (1, 2, 3, 0, 0, 0, 0, 0)
    assert encode_nes_2bpp((row,) * 8) == bytes([0xA0]*8 + [0x60]*8)
    with pytest.raises(PortableCodecError):
        encode_nes_2bpp(((0,)*8,)*7)


def test_decode_nes_2bpp_roundtrip_and_cross_console_order():
    tile = tuple(tuple((x*3+y) % 4 for x in range(8)) for y in range(8))
    assert decode_nes_2bpp(encode_nes_2bpp(tile)) == tile
    assert encode_nes_2bpp(tile) != encode_gb_2bpp(tile)
    with pytest.raises(PortableCodecError):
        decode_nes_2bpp(bytearray(16))


def test_encode_snes_4bpp_high_planes_in_second_bank():
    row = (1, 2, 4, 8, 15, 0, 0, 0)
    expected = bytes([0x88,0x48]*8+[0x28,0x18]*8)
    assert encode_snes_4bpp((row,)*8) == expected
    with pytest.raises(PortableCodecError):
        encode_snes_4bpp(((16,)*8,)*8)


def test_decode_snes_4bpp_recovers_all_palette_indices():
    tile = tuple(tuple((x+y*8) % 16 for x in range(8)) for y in range(8))
    assert decode_snes_4bpp(encode_snes_4bpp(tile)) == tile
    with pytest.raises(PortableCodecError):
        decode_snes_4bpp(b"\x00"*16)


def test_encode_sms_4bpp_row_planes_are_contiguous():
    row = (1, 2, 4, 8, 15, 0, 0, 0)
    assert encode_sms_4bpp((row,)*8) == bytes([0x88,0x48,0x28,0x18]*8)
    assert encode_sms_4bpp((row,)*8) != encode_snes_4bpp((row,)*8)

