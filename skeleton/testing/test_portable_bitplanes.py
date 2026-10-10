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

