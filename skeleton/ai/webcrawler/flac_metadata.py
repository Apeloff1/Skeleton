"""FLAC STREAMINFO measurements only; no audio decode, tags or album art."""
from __future__ import annotations
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

FLAC_TYPES=frozenset({"audio/flac","audio/x-flac"})


def extract_flac(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<42
            or type(max_chars) is not int or max_chars<1
            or body[:4]!=b"fLaC"):
        raise ResearchFormatError("invalid FLAC container")
    meta=body[4]
    length=int.from_bytes(body[5:8],"big")
    if (meta&0x7f)!=0 or length!=34 or 8+length>len(body):
        raise ResearchFormatError("FLAC must start with bounded STREAMINFO")
    info=body[8:42]
    min_block=int.from_bytes(info[0:2],"big")
    max_block=int.from_bytes(info[2:4],"big")
    packed=int.from_bytes(info[10:18],"big")
    sample_rate=(packed>>44)&0xfffff
    channels=1+((packed>>41)&0x7)
    bit_depth=1+((packed>>36)&0x1f)
    samples=packed&((1<<36)-1)
    if (not 16<=min_block<=max_block<=65535
            or not 8000<=sample_rate<=384000
            or not 1<=channels<=8 or not 4<=bit_depth<=32
            or samples<1):
        raise ResearchFormatError("invalid FLAC STREAMINFO values")
    return project_lines([
        "Audio kind: FLAC STREAMINFO",
        f"Channels: {channels}; sampling_hz: {sample_rate}; bits: {bit_depth}",
        f"Samples declared: {samples}; estimated_duration_seconds: {samples/sample_rate:.3f}",
        f"Block size range: {min_block} to {max_block}",
        "Audio, pictures, tags and stream frames: not decoded or inspected",
    ],title="FLAC audio metadata",max_chars=max_chars)
