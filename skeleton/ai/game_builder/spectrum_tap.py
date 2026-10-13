"""Deterministic genuine Sinclair ZX Spectrum tape CODE block packer.

Exports exactly the standard two record 48K .TAP layout: a native Spectrum
CODE header followed by Z80 bytes whose load address is $8000. This does
not bundle a commercial Spectrum ROM or pretend to be an autostart BASIC game.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from struct import pack, unpack_from

LOAD = 32768
MAX_CODE_BYTES = 24576
MAGIC_NAME = b"SKELORIGZX"


class SpectrumTapeError(ValueError):
    """Unsafe, malformed or noncanonical original Spectrum tape format."""


def _record(payload: bytes) -> bytes:
    if not 1 <= len(payload) <= 0xFFFF:
        raise SpectrumTapeError("ZX tape block invalid size")
    parity = 0
    for value in payload:
        parity ^= value
    return pack("<H", len(payload) + 1) + payload + bytes((parity,))


def make_tape(binary: bytes) -> bytes:
    if not isinstance(binary, bytes) or not 128 <= len(binary) <= MAX_CODE_BYTES:
        raise SpectrumTapeError("original Z80 program outside safe 48K code budget")
    if not binary.startswith(b"\xFB\xAF\xd3\xfe"):
        raise SpectrumTapeError("expected ZX Z80 EI, XOR A and ULA border OUT startup")
    # Spectrum header: 0x00 flag + CODE (type 3), 10-character tape name,
    # native code length, 16-bit load address, unused second parameter.
    header = bytes((0, 3)) + MAGIC_NAME + pack("<HHH", len(binary), LOAD, 0x8000)
    tape = _record(header) + _record(b"\xFF" + binary)
    verify_tape(tape, binary)
    return tape


def verify_tape(data: bytes, expected_binary: bytes | None = None) -> dict[str, object]:
    if not isinstance(data, bytes) or not 32 <= len(data) < 26000:
        raise SpectrumTapeError("invalid bounded Spectrum CODE tape")
    pos = 0
    blocks: list[bytes] = []
    for _ in range(2):
        if pos + 2 > len(data):
            raise SpectrumTapeError("missing Spectrum tape length prefix")
        length = unpack_from("<H", data, pos)[0]
        pos += 2
        if length < 2 or pos + length > len(data):
            raise SpectrumTapeError("Spectrum tape record truncated")
        block = data[pos:pos+length]
        pos += length
        parity = 0
        for byte in block:
            parity ^= byte
        if parity:
            raise SpectrumTapeError("Spectrum tape parity corrupted")
        blocks.append(block)
    if pos != len(data):
        raise SpectrumTapeError("unexpected appended Spectrum tape data")
    header, code = blocks
    if len(header) != 19 or header[:12] != bytes((0, 3)) + MAGIC_NAME:
        raise SpectrumTapeError("not an original Spectrum CODE header")
    size, load, unused = unpack_from("<HHH", header, 12)
    if load != LOAD or unused != 0x8000:
        raise SpectrumTapeError("Spectrum tape native load address altered")
    if not 128 <= size <= MAX_CODE_BYTES or len(code) != size + 2 or code[0] != 0xFF:
        raise SpectrumTapeError("Spectrum tape code block size inconsistent")
    payload = code[1:-1]
    if not payload.startswith(b"\xFB\xAF\xd3\xfe"):
        raise SpectrumTapeError("Spectrum tape lacks native original Z80 ULA entry")
    if expected_binary is not None and payload != expected_binary:
        raise SpectrumTapeError("tape code data differs from audited binary")
    return {
        "schema": "skeleton.game_builder.native_spectrum_tap.v1",
        "format": "zx_spectrum_48k_tap_code",
        "tape_sha256": sha256(data).hexdigest(),
        "z80_binary_sha256": sha256(payload).hexdigest(),
        "code_size": len(payload),
        "load_address": load,
        "spectrum_native_header_verified": True,
        "real_z80_opcode_entry_verified": True,
        "rom_firmware_redistributed": False,
        "zx_emulator_playthrough_verified": False,
        "original_hardware_verified": False,
        "distribution_licensed": False,
    }


def get_tape_packer_script() -> str:
    """Export the audited offline packer itself for self-contained projects."""
    return Path(__file__).read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--tap", type=Path, required=True)
    args = parser.parse_args()
    if args.tap.exists() or args.tap.is_symlink():
        raise FileExistsError(str(args.tap))
    data = make_tape(args.code.read_bytes())
    with args.tap.open("xb") as stream:
        stream.write(data)
    print("NATIVE_SPECTRUM_TAPE_CREATED", verify_tape(data)["tape_sha256"])


if __name__ == "__main__":
    main()
