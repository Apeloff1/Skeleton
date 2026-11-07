"""Read-only ICO directory dimensions and sizes; no icon pixel decoding."""
from __future__ import annotations
import struct
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

ICO_TYPES=frozenset({"image/x-icon","image/vnd.microsoft.icon"})


def extract_ico(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<22
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("ICO container size invalid")
    reserved,kind,count=struct.unpack("<HHH",body[:6])
    if reserved!=0 or kind!=1 or not 1<=count<=64 or len(body)<6+16*count:
        raise ResearchFormatError("ICO directory invalid")
    output=[]
    intervals=[]
    for i in range(count):
        start=6+16*i
        w,h,color_count,_unused,planes,bits,n,offset=struct.unpack(
            "<BBBBHHII",body[start:start+16],
        )
        w=w or 256
        h=h or 256
        if n<8 or offset<6+16*count or offset+n>len(body):
            raise ResearchFormatError("ICO image offset/length invalid")
        intervals.append((offset,offset+n))
        output.append(f"Icon {i+1}: {w} x {h}; bits: {bits}; bytes: {n}")
    order=sorted(intervals)
    if any(order[i][1]>order[i+1][0] for i in range(len(order)-1)):
        raise ResearchFormatError("overlapping ICO image resources")
    return project_lines([
        "Image kind: Windows ICO",
        f"Directory images: {count}",
        *output,
        "Referenced PNG/BMP icon payloads: not decoded",
    ],title="ICO icon metadata",max_chars=max_chars)
