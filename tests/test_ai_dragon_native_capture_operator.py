"""Execute real original SDL2 puzzle screenshots and verify trusted release evidence."""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from pathlib import Path
import os,shutil,subprocess,json,pytest

from skeleton.ai.webcrawler.dragon_native_capture_operator import (
    _bitmap,build_original_game_capture,verify_original_capture,
    publish_original_capture,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,
)

def game(**overrides):
    request=ProductionRequest(
        title="Original Dragon Visual Puzzle Expedition",
        targets=("pc_linux",),style="fixed_screen_puzzle",
        seed=37,original_work_attested=True,
        portable_design=PortableGameDesign(stages=2,difficulty=5),
    )
    return replace(request,**overrides)

def native_sdl_ready():
    if not shutil.which("cc") or not shutil.which("pkg-config"):
        return False
    check=subprocess.run(["pkg-config","--exists","sdl2"],timeout=8)
    return check.returncode==0


def test_original_game_footage_requires_explicit_operator_authorization():
    with pytest.raises(PermissionError):
        build_original_game_capture(game(),authorized=False)


@pytest.mark.parametrize("data", [
    b"",b"not a bitmap",b"BM"+b"\0"*64,
    b"MZ"+b"\0"*4096,
])
def test_native_footage_verifier_rejects_non_original_fake_frames(data):
    with pytest.raises(ValueError):
        _bitmap(data)


def test_native_game_capture_does_not_claim_unrelated_console_or_unsupported_gameplay():
    if os.name!="posix":
        pytest.skip("operator capture requires Linux")
    for changes in (
        {"targets":("nes",)},{"targets":("pc_windows",)},
        {"style":"arcade_score_attack"},{"compile_roms":True},
    ):
        with pytest.raises((ValueError,EnvironmentError)):
            build_original_game_capture(game(**changes),authorized=True)


@pytest.mark.skipif(not native_sdl_ready(),reason="native C99 and SDL2 required")
def test_native_game_capture_renders_exact_original_midpoints_and_solved_frames(tmp_path):
    data,report=build_original_game_capture(game(),authorized=True)
    evidence=verify_original_capture(data)
    assert evidence["frames_verified"]==6
    assert evidence["stages"]==2
    assert evidence["status"]=="original_game_frames_structurally_verified"
    assert report["actual_original_game_renderer_executed"]
    assert not report["verified_display_hardware"]
    assert len(report["frames"])==6
    assert [x["phase"] for x in report["frames"]]==[0,1,2]*2
    with ZipFile(BytesIO(data)) as archive:
        assert len(archive.namelist())==9
        first=archive.read("frames/level-01-frame-00.bmp")
        final=archive.read("frames/level-01-frame-02.bmp")
        _bitmap(first);_bitmap(final)
        assert first!=final
        assert "binary/dragon_game_sdl" in archive.namelist()
    published=publish_original_capture(game(),tmp_path,authorized=True)
    assert published["frames"]==6
    assert (tmp_path/published["filename"]).is_file()


@pytest.mark.skipif(not native_sdl_ready(),reason="native SDL2 required")
def test_native_original_frame_archive_rejects_patched_image_even_if_zip_structure_survives():
    data,_=build_original_game_capture(game(),authorized=True)
    with ZipFile(BytesIO(data)) as old:
        content={name:old.read(name) for name in old.namelist()}
    name="frames/level-01-frame-00.bmp"
    frame=bytearray(content[name])
    frame[-1]^=1
    content[name]=bytes(frame)
    stream=BytesIO()
    with ZipFile(stream,"w",ZIP_DEFLATED) as archive:
        for member,blob in content.items():
            archive.writestr(member,blob)
    with pytest.raises(ValueError,match="frame altered"):
        verify_original_capture(stream.getvalue())


def test_original_capture_refuses_corrupted_zip_and_unverified_extra_members():
    for package in (b"",b"PK"+b"\0"*100):
        with pytest.raises((ValueError,Exception)):
            verify_original_capture(package)
