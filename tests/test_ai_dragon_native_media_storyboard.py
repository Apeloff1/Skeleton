"""Generate shareable PNG contact sheets from genuinely executed original SDL2 game."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from pathlib import Path
import shutil,subprocess,struct,pytest

from skeleton.ai.webcrawler.dragon_native_media_storyboard import (
    _bitmap,_pixels,_png_rgb,
    render_original_storyboard,publish_original_storyboard,
    verify_original_storyboard,PNG_HEADER,
)
from skeleton.ai.webcrawler.dragon_native_capture_operator import (
    build_original_game_capture,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,
)

def game(stages=2):
    return ProductionRequest(
        title="Original Pixel Expedition",
        targets=("pc_linux",),style="fixed_screen_puzzle",
        seed=24,original_work_attested=True,
        portable_design=PortableGameDesign(stages=stages,difficulty=6),
    )

def can_render():
    if not shutil.which("cc") or not shutil.which("pkg-config"):
        return False
    result=subprocess.run(["pkg-config","--exists","sdl2"],timeout=8)
    return result.returncode==0

def test_storyboard_png_encoder_generates_real_bounded_rgb_image():
    raw=bytes([28,104,190])*(480*120)
    image=_png_rgb(480,120,raw)
    assert image.startswith(PNG_HEADER)
    assert image[-12:-8]==b"\x00\x00\x00\x00"
    assert struct.unpack_from(">II",image,16)==(480,120)
    assert len(image)<3_000_000

@pytest.mark.parametrize("width,height",[(200,120),(480,0),(480,961)])
def test_png_encoder_rejects_noncanonical_native_campaign_dimensions(width,height):
    with pytest.raises(ValueError):
        _png_rgb(width,height,b"\0"*100)

@pytest.mark.skipif(not can_render(),reason="native SDL2 build prerequisite missing")
def test_real_source_gameplay_frames_produce_true_original_png_storyboard(tmp_path):
    package,receipt=build_original_game_capture(game(),authorized=True)
    bitmap,evidence=render_original_storyboard(package)
    assert bitmap.startswith(PNG_HEADER)
    assert struct.unpack_from(">II",bitmap,16)==(480,240)
    assert evidence["frame_count"]==6
    assert evidence["stages"]==2
    assert evidence["columns"]==3
    assert evidence["png_bytes"]==len(bitmap)
    result=publish_original_storyboard(package,tmp_path,authorized=True)
    assert result["status"]=="original_game_storyboard_generated"
    image=(tmp_path/result["image"]).read_bytes()
    assert image==bitmap
    archive=(tmp_path/result["archive"]).read_bytes()
    review=verify_original_storyboard(archive)
    assert review["status"]=="verified_source_derived_original_game_storyboard"
    assert review["frames"]==6
    assert review["image_sha256"]==result["image_sha256"]


@pytest.mark.skipif(not can_render(),reason="native SDL2 build prerequisite missing")
def test_verifier_refuses_painted_fake_storyboard_even_with_valid_zip(tmp_path):
    package,_=build_original_game_capture(game(1),authorized=True)
    report=publish_original_storyboard(package,tmp_path,authorized=True)
    original=(tmp_path/report["archive"]).read_bytes()
    with ZipFile(BytesIO(original)) as archive:
        members={x:archive.read(x) for x in archive.namelist()}
    image=bytearray(members["original-storyboard.png"])
    image[-15]^=1
    members["original-storyboard.png"]=bytes(image)
    out=BytesIO()
    with ZipFile(out,"w",ZIP_DEFLATED) as archive:
        for key,val in members.items():
            archive.writestr(key,val)
    with pytest.raises(ValueError,match="pixels or evidence"):
        verify_original_storyboard(out.getvalue())


def test_storyboard_publication_requires_rights_authorization(tmp_path):
    with pytest.raises(PermissionError):
        publish_original_storyboard(b"not a native capture",tmp_path,authorized=False)
    assert not tmp_path.exists()
