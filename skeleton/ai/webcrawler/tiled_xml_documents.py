"""Finite TMX/TSX game source metrics, with no external asset path traversal."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .research_projection import (
    ResearchFormatError,ResearchProjection,check_text,project_lines,
)
from .tiled_map_contracts import TiledAccumulator,project_tiled_map

TMX_TYPES=frozenset({"application/x-tiled-tmx+xml","text/x-tiled-tmx"})
TSX_TYPES=frozenset({"application/x-tiled-tsx+xml","text/x-tiled-tsx"})
TILED_XML_TYPES=TMX_TYPES | TSX_TYPES
_FORBIDDEN=re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b",re.I)


def _int(value:object,label:str,low:int,high:int)->int:
    if not isinstance(value,str) or not value.isdecimal() or len(value)>12:
        raise ResearchFormatError("Tiled "+label+" is not finite integer")
    number=int(value)
    if not low<=number<=high:
        raise ResearchFormatError("Tiled "+label+" out of finite bounds")
    return number


def _tree(raw:str)->ET.Element:
    if _FORBIDDEN.search(raw) or len(raw.encode("utf-8"))>1_048_576:
        raise ResearchFormatError("Tiled XML DTD/entity or size exceeds bound")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,RecursionError) as exc:
        raise ResearchFormatError("malformed Tiled source XML") from exc
    count=0
    stack=[(root,1)]
    while stack:
        node,depth=stack.pop()
        count+=1
        if count>16384 or depth>32:
            raise ResearchFormatError("Tiled XML elements/depth exceeded")
        stack.extend((child,depth+1) for child in node)
    if "}" in root.tag:
        raise ResearchFormatError("Tiled XML unexpected root namespace")
    return root


def _csv(raw:str,expected:int)->list[int]:
    if not isinstance(raw,str) or len(raw)>1_048_576:
        raise ResearchFormatError("Tiled CSV source text too large")
    tokens=[x.strip() for x in raw.replace("\r","").replace("\n","").split(",")]
    if tokens[-1]=="":
        tokens.pop()
    if len(tokens)!=expected:
        raise ResearchFormatError("Tiled CSV tile count inconsistent with map")
    return [_int(x,"GID",0,0xFFFFFFFF) for x in tokens]


def _data(node:ET.Element,*,width:int,height:int)->list[int]:
    if node.tag!="data":
        raise ResearchFormatError("Tiled layer data absent")
    encoding=node.get("encoding","")
    if node.get("compression"):
        raise ResearchFormatError("compressed Tiled tile streams not imported")
    if encoding=="csv":
        return _csv(node.text or "",width*height)
    if encoding=="":
        tiles=list(node)
        if len(tiles)!=width*height or any(x.tag!="tile" for x in tiles):
            raise ResearchFormatError("Tiled XML tile cell count invalid")
        return [_int(x.get("gid"),"tile GID",0,0xFFFFFFFF) for x in tiles]
    raise ResearchFormatError("Tiled base64 or unknown encoding disabled")


def _group_items(root:ET.Element):
    stack=[(item,0) for item in reversed(list(root)) if item.tag in (
        "layer","objectgroup","imagelayer","group",
    )]
    while stack:
        item,depth=stack.pop()
        if depth>16:
            raise ResearchFormatError("Tiled group nesting exceeded")
        if item.tag=="group":
            stack.extend((child,depth+1) for child in reversed(list(item))
                         if child.tag in ("layer","objectgroup","imagelayer","group"))
        else:
            yield item


def extract_tmx(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    root=_tree(raw)
    if root.tag!="map" or root.get("orientation") not in (
        "orthogonal","isometric","staggered","hexagonal",
    ):
        raise ResearchFormatError("Tiled XML map kind/orientation unsupported")
    infinite=root.get("infinite","0")=="1"
    acc=TiledAccumulator(
        tile_width=_int(root.get("tilewidth"),"tilewidth",1,1024),
        tile_height=_int(root.get("tileheight"),"tileheight",1,1024),
        width=_int(root.get("width"),"width",0,65536),
        height=_int(root.get("height"),"height",0,65536),
        infinite=infinite,kind="Tiled TMX map",
    )
    for entry in root.findall("tileset"):
        firstgid=_int(entry.get("firstgid"),"tileset firstgid",1,0x1FFFFFFF)
        acc.tileset()
        # External TSX, image, embedded tile definitions are counted only.
    for item in _group_items(root):
        if item.tag=="imagelayer":
            acc.image_layer()
        elif item.tag=="objectgroup":
            acc.layer()
            acc.objects_add(len(item.findall("object")))
        else:
            acc.layer()
            data=item.find("data")
            if data is None:
                raise ResearchFormatError("TMX tile layer has no data")
            if infinite:
                chunks=data.findall("chunk")
                if len(chunks)>256 or not chunks:
                    raise ResearchFormatError("infinite TMX chunk count invalid")
                if data.get("encoding") not in ("csv",None):
                    raise ResearchFormatError("TMX infinite encoded chunks unsupported")
                for chunk in chunks:
                    x=int(chunk.get("x","-999999999"))
                    y=int(chunk.get("y","-999999999"))
                    acc.chunk(x,y)
                    width=_int(chunk.get("width"),"chunk width",1,65536)
                    height=_int(chunk.get("height"),"chunk height",1,65536)
                    values=_csv(chunk.text or "",width*height)
                    acc.tile_data(values,width=width,height=height)
            else:
                width=_int(item.get("width"),"layer width",1,65536)
                height=_int(item.get("height"),"layer height",1,65536)
                if width!=acc.width or height!=acc.height:
                    raise ResearchFormatError("finite TMX layer dimensions differ from map")
                acc.tile_data(_data(data,width=width,height=height),
                              width=width,height=height)
    return project_tiled_map(acc.result(),max_chars=max_chars)


def extract_tsx(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    root=_tree(raw)
    if root.tag!="tileset":
        raise ResearchFormatError("Tiled TSX root tileset missing")
    tilewidth=_int(root.get("tilewidth"),"tilewidth",1,1024)
    tileheight=_int(root.get("tileheight"),"tileheight",1,1024)
    total=_int(root.get("tilecount"),"tilecount",1,65536)
    columns=_int(root.get("columns"),"columns",0,65536)
    declarations=root.findall("tile")
    if len(declarations)>1024:
        raise ResearchFormatError("TSX tile declarations exceed capacity")
    frames=0
    for tile in declarations:
        _int(tile.get("id"),"tile ID",0,65535)
        for animation in tile.findall("animation"):
            frames+=len(animation.findall("frame"))
            if frames>4096:
                raise ResearchFormatError("Tiled frame inventory exceeds bound")
    images=len(root.findall("image"))+sum(len(tile.findall("image"))
                                          for tile in declarations)
    return project_lines([
        "Game source: Tiled TSX tileset declaration",
        f"Tiles declared: {total}; explicit tile entries: {len(declarations)}",
        f"Tile dimensions: {tilewidth} x {tileheight}; columns: {columns}",
        f"Animation frame declarations: {frames}; image references: {images}",
        "Source image paths, animations, tiles and rendering: not loaded",
    ],title="Tiled TSX tileset",max_chars=max_chars)
