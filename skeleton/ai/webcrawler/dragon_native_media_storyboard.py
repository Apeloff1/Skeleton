"""Offline visual storyboard of actual Dragon-generated native gameplay.

Converts independently verified native SDL2 BMP game frames into a bounded
PNG contact sheet using only Python stdlib, not a screenshot of the user's
desktop or a third-party video. Frame order is start/mid/solved for each
original puzzle stage. Every storyboard can be regenerated exactly from
the source capture archive.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import json,struct,zlib

from .dragon_native_capture_operator import (
    verify_original_capture,_bitmap,
)
from .dragon_native_production import _hash,_canonical,_zipinfo,_atomic_new

SCHEMA="skeleton.ai.dragon.original_game_storyboard.v1"
SCALE=4
CELL_W=160
CELL_H=120
COLUMNS=3
MAX_STAGES=8
MAX_PNG=3_000_000
MAX_PACKAGE=24_000_000
PNG_HEADER=b"\x89PNG\r\n\x1a\n"


def _pixels(raw:bytes)->bytes:
    """Decode actual SDL BMP RGB, preserving top-to-bottom image orientation."""
    _bitmap(raw)
    offset=struct.unpack_from("<I",raw,10)[0]
    width,height=struct.unpack_from("<ii",raw,18)
    bits=struct.unpack_from("<H",raw,28)[0]
    compression=struct.unpack_from("<I",raw,30)[0]
    if compression not in (0,3):
        raise ValueError("native BMP compression mode is unsupported")
    if compression==3:
        # Bitfield masks are supported only when they describe the common
        # standard 8-bit components within a 32-bit bitmap.
        if bits!=32 or offset<66:
            raise ValueError("native BMP bitfield layout invalid")
        red,green,blue=struct.unpack_from("<III",raw,54)
        valid_masks={0x00ff0000,0x0000ff00,0x000000ff,0xff000000}
        if len({red,green,blue})!=3 or not {red,green,blue}<=valid_masks:
            raise ValueError("original frame needs non-overlapping 8-bit masks")
        shifts=[mask.bit_length()-8 for mask in (red,green,blue)]
    else:
        shifts=[16,8,0]
    step=bits//8
    stride=((width*bits+31)//32)*4
    output=bytearray(CELL_W*CELL_H*3)
    height_abs=abs(height)
    for y in range(CELL_H):
        py=y*SCALE
        in_y=(height_abs-1-py) if height>0 else py
        for x in range(CELL_W):
            px=x*SCALE
            pointer=offset+in_y*stride+px*step
            if bits==24:
                blue,green,red=raw[pointer:pointer+3]
                rgb=(red,green,blue)
            elif compression==3:
                packed=struct.unpack_from("<I",raw,pointer)[0]
                rgb=tuple((packed>>shift)&255 for shift in shifts)
            else:
                blue,green,red=raw[pointer:pointer+3]
                rgb=(red,green,blue)
            index=(y*CELL_W+x)*3
            output[index:index+3]=bytes(rgb)
    return bytes(output)


def _chunk(tag:bytes,body:bytes)->bytes:
    payload=tag+body
    return (struct.pack(">I",len(body))+payload+
            struct.pack(">I",zlib.crc32(payload)&0xffffffff))


def _png_rgb(width:int,height:int,rgb:bytes)->bytes:
    if (width!=COLUMNS*CELL_W or type(height) is not int or
            not CELL_H<=height<=MAX_STAGES*CELL_H or
            len(rgb)!=width*height*3):
        raise ValueError("original storyboard pixels exceed expected canvas geometry")
    encoded=bytearray()
    for y in range(height):
        encoded.append(0)
        offset=y*width*3
        encoded.extend(rgb[offset:offset+width*3])
    ihdr=struct.pack(">IIBBBBB",width,height,8,2,0,0,0)
    result=(PNG_HEADER+_chunk(b"IHDR",ihdr)+
            _chunk(b"IDAT",zlib.compress(bytes(encoded),level=9))+
            _chunk(b"IEND",b""))
    if len(result)>MAX_PNG:
        raise ValueError("original game storyboard PNG too large")
    return result


@dataclass(frozen=True)
class OriginalStoryboard:
    schema:str
    source_capture_sha256:str
    original_sdl_executable_sha256:str
    stages:int
    frame_count:int
    columns:int
    width:int
    height:int
    screenshot_mode:str
    png_sha256:str
    png_bytes:int
    scope:str


def render_original_storyboard(package:bytes)->tuple[bytes,dict]:
    """Actually reconstruct all original native game images from trusted capture."""
    audit=verify_original_capture(package)
    count=audit["frames_verified"]
    stages=audit["stages"]
    if not 1<=stages<=MAX_STAGES or count!=stages*COLUMNS:
        raise ValueError("original game footage has incomplete campaign")
    width=COLUMNS*CELL_W
    height=stages*CELL_H
    pixels=bytearray(width*height*3)
    with ZipFile(BytesIO(package)) as archive:
        for level in range(1,stages+1):
            for phase in range(COLUMNS):
                name=f"frames/level-{level:02d}-frame-{phase:02d}.bmp"
                tile=_pixels(archive.read(name))
                base_y=(level-1)*CELL_H
                base_x=phase*CELL_W
                for line in range(CELL_H):
                    src=line*CELL_W*3
                    dst=((base_y+line)*width+base_x)*3
                    pixels[dst:dst+CELL_W*3]=tile[src:src+CELL_W*3]
    output=_png_rgb(width,height,bytes(pixels))
    receipt=OriginalStoryboard(
        schema=SCHEMA,source_capture_sha256=_hash(package),
        original_sdl_executable_sha256=audit["binary_sha256"],
        stages=stages,frame_count=count,columns=COLUMNS,
        width=width,height=height,
        screenshot_mode="original_native_sdl2_start_mid_solved",
        png_sha256=_hash(output),png_bytes=len(output),
        scope="actual original game screenshots, not hardware-certified video or third-party footage",
    )
    return output,asdict(receipt)


def publish_original_storyboard(package:bytes,destination:Path,*,authorized:bool)->dict:
    if authorized is not True:
        raise PermissionError("explicit original game visual review export permission required")
    root=Path(destination).expanduser().absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("symlink in original game storyboard release destination")
    if root.exists() and not root.is_dir():
        raise ValueError("game storyboard output must be a directory")
    picture,receipt=render_original_storyboard(package)
    evidence=_canonical(receipt)
    release=BytesIO()
    with ZipFile(release,"w",ZIP_DEFLATED,compresslevel=9) as archive:
        archive.writestr(_zipinfo("original-game-capture.zip"),package)
        archive.writestr(_zipinfo("original-storyboard.png"),picture)
        archive.writestr(_zipinfo("storyboard-evidence.json"),evidence)
    raw=release.getvalue()
    if len(raw)>MAX_PACKAGE:
        raise ValueError("original storyboard release exceeds output budget")
    verify_original_storyboard(raw)
    root.mkdir(parents=True,exist_ok=True)
    name="dragon-original-storyboard-"+_hash(raw)[:20]+".zip"
    image_name="dragon-original-storyboard-"+receipt["png_sha256"][:20]+".png"
    _atomic_new(root/name,raw)
    _atomic_new(root/image_name,picture)
    return {
        "schema":SCHEMA,"status":"original_game_storyboard_generated",
        "archive":name,"image":image_name,
        "archive_sha256":_hash(raw),"image_sha256":_hash(picture),
        "stages":receipt["stages"],"frames":receipt["frame_count"],
    }


def verify_original_storyboard(raw:bytes)->dict:
    if not isinstance(raw,bytes) or not 100<=len(raw)<=MAX_PACKAGE:
        raise ValueError("original storyboard archive missing or too large")
    with ZipFile(BytesIO(raw)) as archive:
        info=archive.infolist()
        expected={"original-game-capture.zip","original-storyboard.png",
                  "storyboard-evidence.json"}
        if (len(info)!=3 or {x.filename for x in info}!=expected or
                any(x.flag_bits&1 or
                    ((x.external_attr>>16)&0o170000)==0o120000 or
                    x.file_size>24_000_000 for x in info) or
                sum(x.file_size for x in info)>26_000_000):
            raise ValueError("unsafe or unrecognized native game storyboard members")
        original=archive.read("original-game-capture.zip")
        image=archive.read("original-storyboard.png")
        evidence=json.loads(archive.read("storyboard-evidence.json"))
    recreated,replay=render_original_storyboard(original)
    if not isinstance(evidence,dict) or evidence!=replay or recreated!=image:
        raise ValueError("storyboard pixels or evidence differs from actual game frames")
    return {
        "schema":SCHEMA,"status":"verified_source_derived_original_game_storyboard",
        "image_sha256":_hash(image),
        "source_capture_sha256":_hash(original),
        "stages":replay["stages"],
        "frames":replay["frame_count"],
    }


def main(argv:list[str]|None=None)->int:
    from argparse import ArgumentParser
    parser=ArgumentParser(description="Render actual original game preview PNG contact sheet")
    parser.add_argument("--capture",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--authorize-storyboard",action="store_true")
    args=parser.parse_args(argv)
    result=publish_original_storyboard(
        args.capture.read_bytes(),args.out,
        authorized=args.authorize_storyboard,
    )
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
