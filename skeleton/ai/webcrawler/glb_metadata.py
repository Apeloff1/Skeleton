"""glTF GLB binary envelope + JSON scene inventory with no GPU or buffer decode."""
from __future__ import annotations
import struct
from .research_projection import ResearchFormatError, ResearchProjection
from .gltf_documents import extract_gltf

GLB_TYPES=frozenset({"model/gltf-binary","application/x-gltf-binary"})


def extract_glb(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<20
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("invalid GLB envelope size")
    magic,version,length=struct.unpack("<4sII",body[:12])
    if magic!=b"glTF" or version!=2 or length!=len(body):
        raise ResearchFormatError("unsupported GLB version or byte framing")
    cursor=12
    chunks=[]
    while cursor<len(body):
        if len(chunks)>=4 or cursor+8>len(body):
            raise ResearchFormatError("unbounded GLB chunk count")
        n,kind=struct.unpack("<I4s",body[cursor:cursor+8])
        cursor+=8
        if n%4!=0 or n>len(body)-cursor:
            raise ResearchFormatError("GLB chunk length/alignment invalid")
        chunks.append((kind,body[cursor:cursor+n]))
        cursor+=n
    if not chunks or chunks[0][0]!=b"JSON":
        raise ResearchFormatError("GLB JSON-first chunk missing")
    if any(kind not in (b"JSON",b"BIN\x00") for kind,_ in chunks):
        raise ResearchFormatError("unrecognized GLB chunk")
    if len(chunks)>2 or (len(chunks)==2 and chunks[1][0]!=b"BIN\x00"):
        raise ResearchFormatError("GLB chunk order invalid")
    try:
        text=chunks[0][1].rstrip(b" \t\r\n").decode("utf-8","strict")
    except UnicodeDecodeError as exc:
        raise ResearchFormatError("invalid GLB JSON UTF-8") from exc
    scene=extract_gltf(text,max_chars=max_chars,max_links=0)
    return ResearchProjection(
        text="GLB binary container; payload chunks: "
             +str(len(chunks))+"\n"+scene.text,
        title="GLB scene inventory",truncated=scene.truncated,
    )
