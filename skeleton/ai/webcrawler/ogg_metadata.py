"""Bounded Opus-in-Ogg identification header, no decoding or page replay."""
from __future__ import annotations
import struct
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

OGG_TYPES=frozenset({"audio/ogg","audio/opus"})


def extract_ogg_opus(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<47
            or type(max_chars) is not int or max_chars<1
            or body[:4]!=b"OggS" or body[4]!=0):
        raise ResearchFormatError("invalid OggS capture header")
    if body[5]&0x2==0:
        raise ResearchFormatError("Opus identification must start a logical stream")
    count=body[26]
    if not 1<=count<=255 or len(body)<27+count:
        raise ResearchFormatError("Ogg segment table missing")
    sizes=body[27:27+count]
    length=sum(sizes)
    payload_start=27+count
    if length<19 or length>65536 or payload_start+length>len(body):
        raise ResearchFormatError("Ogg first-page payload length invalid")
    ident=body[payload_start:payload_start+length]
    if ident[:8]!=b"OpusHead" or ident[8]!=1 or len(ident)<19:
        raise ResearchFormatError("unsupported Ogg audio identifier")
    channels=ident[9]
    preskip=struct.unpack("<H",ident[10:12])[0]
    nominal_rate=struct.unpack("<I",ident[12:16])[0]
    if not 1<=channels<=8 or nominal_rate>384000:
        raise ResearchFormatError("Opus channel or rate outside bounds")
    return project_lines([
        "Audio kind: Opus-in-Ogg",
        f"Channels: {channels}; input_sampling_hz: {nominal_rate}",
        f"Pre-skip samples: {preskip}",
        "Codec frames, text tags and duration: not decoded or inferred",
    ],title="Ogg Opus metadata",max_chars=max_chars)
