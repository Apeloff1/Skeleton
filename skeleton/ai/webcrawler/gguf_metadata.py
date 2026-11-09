"""Finite, read-only GGUF v3 catalog, no tensor payload decode or model loading.

The scanner parses the GGUF little-endian header, bounded typed metadata
and tensor directory. The source file may contain weight data but this
code never parses weights, runs inference, decodes tokens, or trusts model
metadata as permission to download or execute providers.
"""
from __future__ import annotations
from collections import Counter
import struct

from .research_projection import ResearchFormatError,ResearchProjection,project_lines

GGUF_TYPES=frozenset({"application/vnd.gguf","application/x-gguf"})
_MAX_BYTES=2_097_152
_MAX_KV=128
_MAX_TENSORS=512
_MAX_HEADER=1_048_576
_ELEMENT_WIDTH={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}


class _Reader:
    def __init__(self,data:bytes):
        self.data=data
        self.pos=0

    def take(self,n:int)->bytes:
        if (type(n) is not int or n<0 or self.pos+n>len(self.data)
                or self.pos+n>_MAX_BYTES):
            raise ResearchFormatError("GGUF metadata truncated or unbounded")
        value=self.data[self.pos:self.pos+n]
        self.pos+=n
        return value

    def u32(self)->int:
        return struct.unpack("<I",self.take(4))[0]

    def u64(self)->int:
        return struct.unpack("<Q",self.take(8))[0]

    def string(self,*,limit:int=4096)->str:
        length=self.u64()
        if length>limit:
            raise ResearchFormatError("GGUF string width exceeds metadata bound")
        try:
            text=self.take(length).decode("utf-8","strict")
        except UnicodeError as exc:
            raise ResearchFormatError("GGUF string UTF-8 invalid") from exc
        if "\x00" in text or len(text)>limit:
            raise ResearchFormatError("GGUF string contains invalid control or width")
        return text

    def skip(self,kind:int,*,depth:int=0)->None:
        if depth>2:
            raise ResearchFormatError("GGUF metadata array nesting exceeded")
        if kind in _ELEMENT_WIDTH:
            self.take(_ELEMENT_WIDTH[kind])
        elif kind==8:
            self.string()
        elif kind==9:
            element_type=self.u32()
            count=self.u64()
            if count>4096 or element_type==9 and depth>=2:
                raise ResearchFormatError("GGUF array capacity exceeded")
            for _ in range(count):
                self.skip(element_type,depth=depth+1)
        else:
            raise ResearchFormatError("GGUF metadata value type unsupported")
        if self.pos>_MAX_HEADER:
            raise ResearchFormatError("GGUF metadata header byte budget exceeded")


def extract_gguf(
    raw:bytes,*,max_chars:int=524288,
)->ResearchProjection:
    if (type(raw) is not bytes or not 24<=len(raw)<=_MAX_BYTES
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("GGUF source exceeds safe capacity")
    reader=_Reader(raw)
    if reader.take(4)!=b"GGUF":
        raise ResearchFormatError("GGUF magic missing")
    version=reader.u32()
    if version!=3:
        raise ResearchFormatError("only little-endian GGUF v3 metadata is admitted")
    tensor_count=reader.u64()
    metadata_count=reader.u64()
    if not 1<=tensor_count<=_MAX_TENSORS or metadata_count>_MAX_KV:
        raise ResearchFormatError("GGUF declared tensor/metadata capacity invalid")
    metadata_types=Counter()
    seen_keys=set()
    alignment=32
    for _ in range(metadata_count):
        key=reader.string(limit=256)
        if not key or key in seen_keys:
            raise ResearchFormatError("GGUF duplicate or empty metadata key")
        seen_keys.add(key)
        kind=reader.u32()
        if key=="general.alignment":
            if kind!=4:
                raise ResearchFormatError("GGUF tensor alignment type invalid")
            alignment=reader.u32()
            if alignment<8 or alignment>4096 or (alignment & (alignment-1))!=0:
                raise ResearchFormatError("GGUF alignment not a safe power of two")
        else:
            reader.skip(kind)
        metadata_types[kind]+=1
    if reader.pos>_MAX_HEADER:
        raise ResearchFormatError("GGUF metadata size exceeds header limit")
    shape_dimensions=Counter()
    tensor_types=Counter()
    seen_tensors=set()
    declared_elements=0
    largest_offset=0
    for _ in range(tensor_count):
        name=reader.string(limit=256)
        if not name or name in seen_tensors:
            raise ResearchFormatError("GGUF tensor names duplicated or absent")
        seen_tensors.add(name)
        dimensions=reader.u32()
        if not 1<=dimensions<=8:
            raise ResearchFormatError("GGUF tensor dimension count invalid")
        elements=1
        for _ in range(dimensions):
            extent=reader.u64()
            if extent<1 or extent>1_000_000_000:
                raise ResearchFormatError("GGUF shape extent invalid")
            elements*=extent
            if elements>1_000_000_000:
                raise ResearchFormatError("GGUF tensor element product exceeds bound")
        tensor_type=reader.u32()
        if tensor_type>512:
            raise ResearchFormatError("GGUF unknown tensor encoding class")
        offset=reader.u64()
        if offset%alignment!=0 or offset>1<<52:
            raise ResearchFormatError("GGUF tensor offset invalid")
        shape_dimensions[dimensions]+=1
        tensor_types[tensor_type]+=1
        declared_elements+=elements
        largest_offset=max(largest_offset,offset)
        if declared_elements>4_000_000_000:
            raise ResearchFormatError("GGUF claimed parameter count exceeds bound")
    if reader.pos>_MAX_HEADER:
        raise ResearchFormatError("GGUF tensor directory exceeds header bound")
    # The tensor data region is intentionally not parsed: large models
    # exceed canonical request caps. A directory is not verified weights.
    lines=[
        "ML artifact: GGUF v3 header-only source inventory",
        f"Tensors declared: {tensor_count}; metadata fields: {metadata_count}",
        f"Claimed scalar/quantized elements: {declared_elements}",
        f"Tensor header bytes parsed: {reader.pos}; source bytes: {len(raw)}",
        f"Declared data alignment: {alignment}; "
        f"largest tensor directory offset: {largest_offset}",
        "Tensor dimension counts: "+", ".join(
            f"{kind}D={count}" for kind,count in sorted(shape_dimensions.items())
        ),
        "Encoded tensor type identifiers: "+", ".join(
            f"{key}={count}" for key,count in sorted(tensor_types.items())
        ),
        "Metadata values, tensor names, weights and model execution: omitted",
        "Header declarations are not proof of payload integrity or training rights",
    ]
    return project_lines(lines,title="GGUF model inventory",max_chars=max_chars)
