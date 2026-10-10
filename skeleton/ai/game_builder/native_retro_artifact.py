"""Original-homebrew cartridge and tape format checks across six retro systems.

No commercial ROM, firmware, official boot-logo bytes or proprietary toolchain
is supplied. File examination is limited to local, no-follow, bounded bytes.
Header recognition, checksum validation and reset-vector inspection are NOT
evidence of gameplay, hardware acceptance, title ownership or release rights.

Implemented formats: DMG, CGB, NES NROM mapper 0, SMS 32 KiB, MSX1 page-1
16 KiB and ZX Spectrum 48K native two-record CODE tape.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import struct

from .native_release_intake import _read_bounded
from .msx1_rom import verify_msx1_rom, MSX1ROMError
from .sms_rom import verify_sms, SMSROMError
from .spectrum_tap import verify_tape, SpectrumTapeError


_SUPPORTED = {
    "nintendo_game_boy":"GB_DMG",
    "nintendo_game_boy_color":"GB_CGB",
    "nintendo_famicom":"NES_NROM",
    "sega_master_system":"SMS_Z80_32K",
    "msx1":"MSX1_Z80_16K",
    "sinclair_zx_spectrum":"SPECTRUM_TAP",
}
_MAX_RETRO = 9 * 1024 * 1024


class RetroArtifactError(ValueError):
    """Unsafe, malformed, unexpected or unreviewed homebrew native artifact."""


@dataclass(frozen=True, slots=True)
class RetroArtifactReceipt:
    target_platform_id: str
    native_format: str
    artifact_sha256: str
    artifact_size: int
    header_and_layout_checked: bool = True
    header_authenticity_proven: bool = False
    emulator_gameplay_verified: bool = False
    physical_hardware_verified: bool = False
    copied_asset_free_certified: bool = False
    licensed_distribution_authorized: bool = False

    def __post_init__(self) -> None:
        if self.target_platform_id not in _SUPPORTED:
            raise RetroArtifactError("retro receipt platform unsupported")
        if self.native_format != _SUPPORTED[self.target_platform_id]:
            raise RetroArtifactError("retro receipt platform-format mismatch")
        if not isinstance(self.artifact_sha256,str) or len(self.artifact_sha256)!=64 or any(
            value not in "0123456789abcdef" for value in self.artifact_sha256
        ):
            raise RetroArtifactError("retro receipt artifact SHA-256 malformed")
        if type(self.artifact_size) is not int or not 32 <= self.artifact_size <= _MAX_RETRO:
            raise RetroArtifactError("retro receipt byte budget invalid")
        if self.header_and_layout_checked is not True or any(
            getattr(self,field) is not False for field in (
                "header_authenticity_proven","emulator_gameplay_verified",
                "physical_hardware_verified","copied_asset_free_certified",
                "licensed_distribution_authorized",
            )
        ):
            raise RetroArtifactError("native ROM metadata cannot automatically grant legal/hardware clearance")

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.retro_native_intake.v1",
            "target_platform_id":self.target_platform_id,
            "native_format":self.native_format,
            "artifact_sha256":self.artifact_sha256,
            "artifact_size":self.artifact_size,
            "header_and_layout_checked":True,
            "header_authenticity_proven":False,
            "emulator_gameplay_verified":False,
            "physical_hardware_verified":False,
            "copied_asset_free_certified":False,
            "licensed_distribution_authorized":False,
        }


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RetroArtifactError(reason)


def _gameboy(data: bytes, *, color_only: bool) -> None:
    _require(len(data)>=32768 and len(data)<=_MAX_RETRO and len(data)%16384==0,
             "Game Boy cartridge must have a valid bank-aligned ROM size")
    code=data[0x148]
    if code<=8:
        declared=32768<<code
    elif code in (0x52,0x53,0x54):
        declared={0x52:72,0x53:80,0x54:96}[code]*16384
    else:
        raise RetroArtifactError("unrecognized Game Boy cartridge ROM size code")
    _require(declared==len(data), "Game Boy cartridge header size differs from actual ROM")
    _require(data[0x147] in {
        0x00,0x01,0x02,0x03,0x05,0x06,0x08,0x09,0x0F,0x10,0x11,
        0x12,0x13,0x19,0x1A,0x1B,0x1C,0x1D,0x1E,
    }, "Game Boy mapper unknown or unsupported")
    _require(data[0x143] in (0x00,0x80,0xC0),
             "Game Boy CGB capability flag invalid for scoped homebrew")
    if color_only:
        _require(data[0x143] in (0x80,0xC0),
                 "CGB-targeted cartridge does not declare color compatibility")
    else:
        _require(data[0x143]!=0xC0, "CGB-only game is not a DMG cartridge")
    checksum=0
    for b in data[0x134:0x14D]:
        checksum=(checksum-b-1)&0xFF
    _require(checksum==data[0x14D], "Game Boy cartridge header checksum mismatch")
    _require(any(data[0x100:0x104]) and data[0x100:0x104]!=b"\xff"*4,
             "Game Boy reset entry lacks real 8-bit machine bytes")
    # Official Nintendo logo bytes/approval are deliberately not supplied,
    # compared or redistributable through this metadata verifier.


def _nes(data: bytes) -> None:
    _require(len(data)>=16+16384, "NES cartridge lacks native PRG ROM")
    _require(data[:4]==b"NES\x1A", "NES cartridge iNES identifier invalid")
    nprg,nchr,flags6,flags7=data[4:8]
    _require(1<=nprg<=2 and 0<=nchr<=1,
             "NES parser admits only 16KB/32KB mapper-0 native NROM")
    _require(flags6 & 0xFC == 0 and flags7 == 0,
             "NES ROM has unreviewed mapper, trainer, console mode or NES2 metadata")
    _require(data[8:16]==b"\x00"*8,"NES iNES1 reserved metadata must be canonical zeroes")
    prg=nprg*16384
    chr_bytes=nchr*8192
    _require(len(data)==16+prg+chr_bytes,
             "NES PRG/CHR bank count differs from actual native cartridge size")
    reset=struct.unpack_from("<H",data,16+prg-4)[0]
    _require(0x8000<=reset<=0xFFFF, "NES reset vector points outside cartridge CPU memory")
    if nprg==1:
        reset=0x8000+(reset-0x8000)%16384
    reset_offset=16+(reset-0x8000)
    _require(reset_offset < 16+prg and data[reset_offset] not in (0x00,0xFF),
             "NES reset vector targets empty or unsupported native code")
    _require(any(x not in (0,0xFF) for x in data[16:16+prg]),
             "NES cartridge lacks plausible original CPU instruction bytes")


def inspect_original_retro_artifact(
    path: str | Path, *, target_platform_id: str, expected_sha256: str,
) -> RetroArtifactReceipt:
    """Validate a real local cartridge/tape's scoped native metadata and hash.

    Does not download any commercial ROMs, include firmware or certify rights.
    """
    if target_platform_id not in _SUPPORTED:
        raise RetroArtifactError("unsupported historical native format")
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or any(
        char not in "0123456789abcdef" for char in expected_sha256
    ):
        raise RetroArtifactError("expected content-addressed original ROM evidence missing")
    size_cap={
        "nintendo_game_boy":_MAX_RETRO,
        "nintendo_game_boy_color":_MAX_RETRO,
        "nintendo_famicom":16+2*16384+8192,
        "sega_master_system":32768,
        "msx1":16384,
        "sinclair_zx_spectrum":26000,
    }[target_platform_id]
    try:
        data=_read_bounded(Path(path),max_bytes=size_cap)
    except (OSError,ValueError) as exc:
        raise RetroArtifactError("cannot safely read bounded local original homebrew image") from exc
    digest=sha256(data).hexdigest()
    _require(digest==expected_sha256,
             "retro ROM/tape bytes changed since independently reviewed source")
    try:
        if target_platform_id=="nintendo_game_boy":
            _gameboy(data,color_only=False)
        elif target_platform_id=="nintendo_game_boy_color":
            _gameboy(data,color_only=True)
        elif target_platform_id=="nintendo_famicom":
            _nes(data)
        elif target_platform_id=="sega_master_system":
            verify_sms(data)
        elif target_platform_id=="msx1":
            verify_msx1_rom(data)
        else:
            verify_tape(data)
    except (SMSROMError,MSX1ROMError,SpectrumTapeError) as exc:
        raise RetroArtifactError("native homebrew artifact has invalid hardware-specific metadata") from exc
    return RetroArtifactReceipt(
        target_platform_id,_SUPPORTED[target_platform_id],digest,len(data),
    )
