"""Structural executable parser tests: authored synthetic PE, ELF and Mach-O.

These files exercise bounded format metadata, NEVER demonstrate an executable
that launches on native hardware, and are not commercially distributed games.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
import struct

import pytest

from skeleton.ai.game_builder.native_binary_structure import (
    ExecutableFormatError, verify_native_executable_structure,
)


def pe_image() -> bytearray:
    b=bytearray(1536)
    b[:2]=b"MZ"
    struct.pack_into("<I",b,0x3C,0x80)
    b[0x80:0x84]=b"PE\x00\x00"
    struct.pack_into("<HHIIIHH",b,0x84,0x8664,1,0,0,0,240,0x0002)
    opt=0x98
    struct.pack_into("<H",b,opt,0x20B)
    struct.pack_into("<I",b,opt+16,0x1000)
    struct.pack_into("<I",b,opt+32,0x1000)
    struct.pack_into("<I",b,opt+36,0x200)
    struct.pack_into("<I",b,opt+56,0x2000)
    struct.pack_into("<I",b,opt+60,0x200)
    sec=opt+240
    b[sec:sec+8]=b".text\x00\x00\x00"
    struct.pack_into("<IIII",b,sec+8,0x200,0x1000,0x200,0x200)
    struct.pack_into("<I",b,sec+36,0x60000020)
    b[0x200]=0xC3
    return b


def elf_image() -> bytearray:
    b=bytearray(512)
    b[:7]=b"\x7fELF\x02\x01\x01"
    struct.pack_into(
        "<HHIQQQIHHHHHH",b,16,
        3,62,1,0x400100,64,0,0,64,56,1,0,0,0,
    )
    struct.pack_into("<IIQQQQQQ",b,64,1,5,0,0x400000,0,512,512,4096)
    b[256]=0xC3
    return b


def macho_image() -> bytearray:
    b=bytearray(512)
    b[:4]=b"\xcf\xfa\xed\xfe"
    struct.pack_into("<IIIIIII",b,4,0x01000007,3,2,2,96,0,0)
    struct.pack_into(
        "<II16sQQQQIIII",b,32,
        0x19,72,b"__TEXT".ljust(16,b"\x00"),
        0x100000000,512,0,512,5,5,0,0,
    )
    struct.pack_into("<IIQQ",b,104,0x80000028,24,256,0)
    b[256]=0xC3
    return b


@pytest.mark.parametrize("target,creator,expected",[
    ("windows_modern",pe_image,"PE/COFF"),
    ("linux_desktop",elf_image,"ELF"),
    ("macos_modern",macho_image,"Mach-O"),
])
def test_real_file_structural_metadata_is_checked_without_claiming_execution(
    tmp_path,target,creator,expected,
):
    data=creator()
    path=tmp_path/"original-test-game"
    path.write_bytes(data)
    result=verify_native_executable_structure(
        path,target_platform_id=target,expected_sha256=sha256(data).hexdigest(),
    )
    assert result.format_name==expected
    assert result.mapped_segments>=1
    assert result.executable_segments>=1
    assert result.entrypoint>0
    assert result.format_structure_checked is True
    assert result.executable_boot_verified is False
    assert result.compiler_origin_verified is False
    assert result.malware_free_certified is False
    assert result.legal_distribution_permitted is False
    assert result.public_receipt()["legal_distribution_permitted"] is False
    assert result==verify_native_executable_structure(
        path,target_platform_id=target,expected_sha256=sha256(data).hexdigest(),
    )
    with pytest.raises(ExecutableFormatError):
        replace(result,executable_boot_verified=True)
    with pytest.raises(ExecutableFormatError):
        replace(result,legal_distribution_permitted=True)


@pytest.mark.parametrize("target,data",[
    ("windows_modern",bytearray(b"MZ"+b"\x00"*1534)),
    ("linux_desktop",bytearray(b"\x7fELF"+b"\x00"*1532)),
    ("macos_modern",bytearray(b"\xcf\xfa\xed\xfe"+b"\x00"*1532)),
])
def test_magic_number_alone_can_never_be_reported_as_structural_image(
    tmp_path,target,data,
):
    path=tmp_path/"magic-only"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            path,target_platform_id=target,expected_sha256=sha256(data).hexdigest(),
        )


@pytest.mark.parametrize("offset,fmt,value",[
    (0x3C,"<I",5000000),
    (0x84,"<H",0),
    (0x86,"<H",97),
    (0x96,"<H",0),
    (0x98,"<H",0),
    (0x98+16,"<I",0),
    (0x98+16,"<I",0x3000),
    (0x98+32,"<I",0),
    (0x98+36,"<I",0),
    (0x98+56,"<I",0x100),
    (0x98+60,"<I",0x100),
    (0x188+8+4,"<I",0x3000),
    (0x188+8+8,"<I",4096),
    (0x188+8+12,"<I",0x123),
    (0x188+36,"<I",0x40000040),
])
def test_windows_pe_structural_mutations_rejected(tmp_path,offset,fmt,value):
    data=pe_image()
    struct.pack_into(fmt,data,offset,value)
    path=tmp_path/"changed-game.exe"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            path,target_platform_id="windows_modern",
            expected_sha256=sha256(data).hexdigest(),
        )


@pytest.mark.parametrize("offset,fmt,value",[
    (4,"B",3),
    (5,"B",3),
    (16,"<H",4),
    (18,"<H",0),
    (24,"<Q",0),
    (24,"<Q",0x800000000000),
    (32,"<Q",5000000),
    (54,"<H",2),
    (56,"<H",0),
    (64+4,"<I",0),
    (64+32,"<Q",1000),
    (64+48,"<Q",10),
])
def test_linux_elf_program_header_mutations_rejected(tmp_path,offset,fmt,value):
    data=elf_image()
    struct.pack_into(fmt,data,offset,value)
    path=tmp_path/"bad"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            path,target_platform_id="linux_desktop",
            expected_sha256=sha256(data).hexdigest(),
        )


@pytest.mark.parametrize("offset,fmt,value",[
    (4,"<I",0),
    (12,"<I",6),
    (16,"<I",5000),
    (20,"<I",5000000),
    (32+4,"<I",0),
    (32+4,"<I",73),
    (32+24+16,"<Q",100000),
    (32+56+4,"<I",0),
    (104+4,"<I",0),
    (104+8,"<Q",600),
])
def test_macos_macho_load_command_mutations_rejected(tmp_path,offset,fmt,value):
    data=macho_image()
    struct.pack_into(fmt,data,offset,value)
    path=tmp_path/"bad-macho"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            path,target_platform_id="macos_modern",
            expected_sha256=sha256(data).hexdigest(),
        )


@pytest.mark.parametrize("target,creator",[
    ("windows_modern",pe_image),("linux_desktop",elf_image),
    ("macos_modern",macho_image),
])
def test_validly_structured_binaries_still_require_exact_byte_hash(tmp_path,target,creator):
    data=creator()
    path=tmp_path/"game"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError,match="differ"):
        verify_native_executable_structure(
            path,target_platform_id=target,expected_sha256="f"*64,
        )


def test_native_parser_rejects_symlinks_hardlinks_and_oversized_sparse_image(tmp_path):
    data=elf_image()
    real=tmp_path/"original-game"
    real.write_bytes(data)
    linked=tmp_path/"linked-game"
    linked.symlink_to(real)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            linked,target_platform_id="linux_desktop",
            expected_sha256=sha256(data).hexdigest(),
        )
    real2=tmp_path/"hardlinked-game"
    os.link(real,real2)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            real2,target_platform_id="linux_desktop",
            expected_sha256=sha256(data).hexdigest(),
        )


def test_wrong_target_platform_is_not_interchangeable(tmp_path):
    data=pe_image()
    path=tmp_path/"game"
    path.write_bytes(data)
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            path,target_platform_id="linux_desktop",
            expected_sha256=sha256(data).hexdigest(),
        )


def test_nonexistent_native_game_image_fails_without_synthesizing_receipt(tmp_path):
    with pytest.raises(ExecutableFormatError):
        verify_native_executable_structure(
            tmp_path/"no-game",
            target_platform_id="windows_modern",expected_sha256="f"*64,
        )
