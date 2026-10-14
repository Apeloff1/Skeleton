"""Real source-derived macOS native Mach-O executable and host gameplay audits."""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
import json,struct,sys,shutil,pytest

from skeleton.ai.webcrawler.dragon_native_macos import (
    MACH64,LC_MAIN,macho64_format,build_native_macos_game,
    verify_native_macos_game,publish_macos_game,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    PortableGameDesign,ProductionRequest,
)

def game(**changes):
    base=ProductionRequest(
        title="Original Native Mac Starlight",
        targets=("pc_macos",),style="fixed_screen_puzzle",seed=37,
        original_work_attested=True,
        portable_design=PortableGameDesign(stages=2,difficulty=8),
    )
    return replace(base,**changes)

def fake_macho(*,machine=0x0100000c,kind=2,main=True):
    data=bytearray(1024)
    struct.pack_into("<IIIIIIII",data,0,
                     MACH64,machine,0,kind,1,24,0,0)
    struct.pack_into("<IIQQ",data,32,
                     LC_MAIN if main else 0x19,24,512,0)
    return bytes(data)


def test_native_macos_parser_requires_real_64bit_executable_structure():
    assert "arm64" in macho64_format(fake_macho())
    assert "x86_64" in macho64_format(fake_macho(machine=0x01000007))
    for data in (b"not macOS",fake_macho(machine=0x99),
                 fake_macho(kind=6),fake_macho(main=False),
                 fake_macho()[:48],
                 b"MZ"+b"\x00"*510):
        with pytest.raises(ValueError):
            macho64_format(data)


def test_original_macos_game_build_requires_authorized_macos_host():
    with pytest.raises(PermissionError):
        build_native_macos_game(game(),authorized=False)
    if sys.platform!="darwin":
        with pytest.raises(OSError):
            build_native_macos_game(game(),authorized=True)


@pytest.mark.skipif(sys.platform!="darwin" or not shutil.which("cc"),
                    reason="requires native macOS host and system C99 compiler")
def test_original_macos_game_is_compiled_executed_and_exactly_replayed(tmp_path):
    packaged,evidence=build_native_macos_game(game(),authorized=True)
    assert evidence["target"]=="pc_macos"
    assert evidence["actual_macos_host_executed"] is True
    assert evidence["macos_hardware_certified"] is False
    assert evidence["native_hint_stages"]==2
    assert evidence["native_branch_endings"]==1
    assert evidence["native_branch_transitions"]==1
    assert len(evidence["branch_output_sha256"])==64
    assert evidence["native_star_grades"]==2
    assert evidence["independent_replays"]==6
    audit=verify_native_macos_game(packaged)
    assert audit["status"]=="macos_compiled_with_host_selftests"
    assert audit["stages_replayed"]==2
    assert audit["architecture"] in ("arm64","x86_64")
    with ZipFile(BytesIO(packaged)) as archive:
        executable=archive.read("binary/dragon_game")
        assert "Mach-O" in macho64_format(executable)
    published=publish_macos_game(game(),tmp_path,authorized=True)
    assert (tmp_path/published["filename"]).is_file()


def test_macos_export_rejects_user_controlled_symlink_even_in_temp_tree(tmp_path):
    actual=tmp_path/"real_destination"
    actual.mkdir()
    alias=tmp_path/"user_alias"
    alias.symlink_to(actual,target_is_directory=True)
    # Must reject before invoking a native compiler or writing any artifact.
    with pytest.raises(ValueError,match="symlinked"):
        publish_macos_game(game(),alias,authorized=True)


@pytest.mark.skipif(sys.platform!="darwin" or not shutil.which("cc"),
                    reason="requires real macOS game build host")
def test_mac_game_archive_rejects_modified_native_binary_even_if_zip_valid():
    package,_=build_native_macos_game(game(),authorized=True)
    with ZipFile(BytesIO(package)) as original:
        rows={name:original.read(name) for name in original.namelist()}
    rows["binary/dragon_game"]=rows["binary/dragon_game"]+b"\x00"
    stream=BytesIO()
    with ZipFile(stream,"w",ZIP_DEFLATED) as zipfile:
        for name,value in rows.items():
            zipfile.writestr(name,value)
    with pytest.raises(ValueError,match="verification"):
        verify_native_macos_game(stream.getvalue())
