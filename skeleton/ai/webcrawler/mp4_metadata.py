"""Conservative ISO BMFF ftyp/movie header inspection, without media decoding.

No media samples, tracks, EXIF, embedded links, subtitle scripts, DRM material
or external references are decoded. Only already-contained bounded box
headers and mvhd timing fields are inspected.
"""
from __future__ import annotations
import struct
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

MP4_TYPES=frozenset({"video/mp4","audio/mp4"})


def _boxes(body: bytes, start: int, end: int):
    pos=start
    count=0
    while pos<end:
        count+=1
        if count>256 or pos+8>end:
            raise ResearchFormatError("MP4 box count/framing exceeded")
        length=int.from_bytes(body[pos:pos+4],"big")
        kind=body[pos+4:pos+8]
        offset=8
        if length==1:
            if pos+16>end:
                raise ResearchFormatError("incomplete extended MP4 box")
            length=int.from_bytes(body[pos+8:pos+16],"big")
            offset=16
        if length<offset or pos+length>end:
            raise ResearchFormatError("MP4 box exceeds container bound")
        yield kind,pos+offset,pos+length
        pos+=length


def extract_mp4(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<32
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("MP4 metadata exceeds finite byte size")
    top=list(_boxes(body,0,len(body)))
    ftyp=next(((start,end) for kind,start,end in top if kind==b"ftyp"),None)
    moov=next(((start,end) for kind,start,end in top if kind==b"moov"),None)
    if ftyp is None or moov is None or ftyp[1]-ftyp[0]<8:
        raise ResearchFormatError("MP4 ftyp/moov boxes missing")
    brand=body[ftyp[0]:ftyp[0]+4]
    if not all(32<=x<127 for x in brand):
        raise ResearchFormatError("invalid MP4 major brand")
    movie=list(_boxes(body,*moov))
    mvhd=next(((start,end) for kind,start,end in movie if kind==b"mvhd"),None)
    if mvhd is None:
        raise ResearchFormatError("MP4 movie header absent")
    data=body[mvhd[0]:mvhd[1]]
    if not data:
        raise ResearchFormatError("empty MP4 movie header")
    if data[0]==0 and len(data)>=20:
        rate=int.from_bytes(data[12:16],"big")
        duration=int.from_bytes(data[16:20],"big")
    elif data[0]==1 and len(data)>=32:
        rate=int.from_bytes(data[20:24],"big")
        duration=int.from_bytes(data[24:32],"big")
    else:
        raise ResearchFormatError("unsupported MP4 movie version or fields")
    if rate<1 or rate>1_000_000 or duration==2**64-1:
        raise ResearchFormatError("invalid MP4 movie timescale")
    return project_lines([
        f"Media container: MP4; major_brand: {brand.decode('ascii')}",
        f"Movie timescale: {rate}; duration_units: {duration}",
        f"Duration_seconds_from_header: {duration/rate:.3f}",
        "Encoded audio/video samples, DRM and timed actions: not decoded",
    ],title="MP4 container metadata",max_chars=max_chars)
