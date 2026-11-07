"""Finite WebP container dimensions without image decode or EXIF access."""
from __future__ import annotations
import struct
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

WEBP_TYPES=frozenset({"image/webp"})


def extract_webp(body: bytes, *, max_chars: int=524288) -> ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<30
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("invalid WebP source size")
    if body[:4]!=b"RIFF" or body[8:12]!=b"WEBP":
        raise ResearchFormatError("not a WebP RIFF container")
    declared=struct.unpack("<I",body[4:8])[0]
    if declared+8!=len(body):
        raise ResearchFormatError("WebP RIFF length mismatch")
    kind=body[12:16]
    size=struct.unpack("<I",body[16:20])[0]
    if size<1 or 20+size>len(body):
        raise ResearchFormatError("truncated WebP first chunk")
    data=body[20:20+size]
    if kind==b"VP8X":
        if len(data)<10:
            raise ResearchFormatError("incomplete extended WebP header")
        w=1+int.from_bytes(data[4:7],"little")
        h=1+int.from_bytes(data[7:10],"little")
        style="extended"
    elif kind==b"VP8 ":
        if len(data)<10 or data[3:6]!=b"\x9d\x01\x2a":
            raise ResearchFormatError("invalid lossy WebP frame header")
        w=struct.unpack("<H",data[6:8])[0]&0x3fff
        h=struct.unpack("<H",data[8:10])[0]&0x3fff
        style="lossy"
    elif kind==b"VP8L":
        if len(data)<5 or data[0]!=0x2f:
            raise ResearchFormatError("invalid lossless WebP frame header")
        bits=int.from_bytes(data[1:5],"little")
        w=1+(bits&0x3fff)
        h=1+((bits>>14)&0x3fff)
        style="lossless"
    else:
        raise ResearchFormatError("unsupported WebP frame encoding")
    if w<1 or h<1 or w>16384 or h>16384 or w*h>67_108_864:
        raise ResearchFormatError("WebP dimensions exceed finite bounds")
    return project_lines([
        f"Image kind: WebP {style}",
        f"Dimensions: {w} x {h}",
        "Pixels, metadata and animation: not decoded or executed",
    ], title="WebP image metadata", max_chars=max_chars)
