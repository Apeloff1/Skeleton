"""Finite Tiled JSON map cell census without textures, code or chunk execution."""
from __future__ import annotations

import json
from typing import Any

from .research_projection import ResearchFormatError,ResearchProjection,check_text
from .tiled_map_contracts import TiledAccumulator,project_tiled_map

TILED_JSON_TYPES=frozenset({
    "application/x-tiled-map+json","application/vnd.tiled.map+json",
})


def _unique(pairs:list[tuple[str,Any]])->dict:
    value={}
    for key,item in pairs:
        if key in value:
            raise ResearchFormatError("duplicate Tiled map JSON key")
        value[key]=item
    return value


def _nonfinite(value:str)->Any:
    raise ResearchFormatError("nonfinite Tiled map JSON constant")


def _int(value:object,name:str,low:int,high:int)->int:
    if type(value) is not int or not low<=value<=high:
        raise ResearchFormatError("Tiled JSON "+name+" integer capacity exceeded")
    return value


def _list(value:object,name:str,maximum:int)->list:
    if not isinstance(value,list) or len(value)>maximum:
        raise ResearchFormatError("Tiled JSON "+name+" exceeds finite list")
    return value


def _tiles(layer:dict,acc:TiledAccumulator)->None:
    if acc.infinite:
        chunks=_list(layer.get("chunks"),"chunks",256)
        if not chunks:
            raise ResearchFormatError("Tiled infinite tilelayer has no bounded chunks")
        for chunk in chunks:
            if not isinstance(chunk,dict):
                raise ResearchFormatError("Tiled JSON chunk must be object")
            x=_int(chunk.get("x"),"chunk x",-1_000_000,1_000_000)
            y=_int(chunk.get("y"),"chunk y",-1_000_000,1_000_000)
            width=_int(chunk.get("width"),"chunk width",1,65536)
            height=_int(chunk.get("height"),"chunk height",1,65536)
            acc.chunk(x,y)
            cells=_list(chunk.get("data"),"chunk GID array",65536)
            acc.tile_data(cells,width=width,height=height)
    else:
        width=_int(layer.get("width"),"layer width",1,65536)
        height=_int(layer.get("height"),"layer height",1,65536)
        if width!=acc.width or height!=acc.height:
            raise ResearchFormatError("Tiled JSON layer dimensions inconsistent")
        acc.tile_data(_list(layer.get("data"),"tile data",65536),
                      width=width,height=height)


def extract_tiled_json(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    try:
        doc=json.loads(raw,object_pairs_hook=_unique,parse_constant=_nonfinite)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("malformed Tiled JSON map") from exc
    if not isinstance(doc,dict) or doc.get("type")!="map":
        raise ResearchFormatError("Tiled JSON root type must be map")
    if doc.get("orientation") not in (
        "orthogonal","isometric","staggered","hexagonal",
    ):
        raise ResearchFormatError("unsupported Tiled JSON map orientation")
    infinite=doc.get("infinite",False)
    if type(infinite) is not bool:
        raise ResearchFormatError("Tiled JSON map mode must be boolean")
    acc=TiledAccumulator(
        tile_width=_int(doc.get("tilewidth"),"tilewidth",1,1024),
        tile_height=_int(doc.get("tileheight"),"tileheight",1,1024),
        width=_int(doc.get("width"),"width",0,65536),
        height=_int(doc.get("height"),"height",0,65536),
        infinite=infinite,kind="Tiled JSON map",
    )
    tilesets=_list(doc.get("tilesets",[]),"tilesets",128)
    for row in tilesets:
        if not isinstance(row,dict):
            raise ResearchFormatError("Tiled JSON tileset reference invalid")
        acc.tileset()
    root=_list(doc.get("layers"),"layers",256)
    stack=[(layer,0) for layer in reversed(root)]
    total=0
    while stack:
        layer,depth=stack.pop()
        total+=1
        if total>512 or depth>16 or not isinstance(layer,dict):
            raise ResearchFormatError("Tiled JSON layer graph capacity exceeded")
        kind=layer.get("type")
        if kind=="group":
            children=_list(layer.get("layers"),"group layers",256)
            stack.extend((child,depth+1) for child in reversed(children))
        elif kind=="tilelayer":
            acc.layer()
            _tiles(layer,acc)
        elif kind=="objectgroup":
            acc.layer()
            objects=_list(layer.get("objects",[]),"objects",2048)
            if any(not isinstance(row,dict) for row in objects):
                raise ResearchFormatError("Tiled JSON object entry invalid")
            acc.objects_add(len(objects))
        elif kind=="imagelayer":
            acc.image_layer()
        else:
            raise ResearchFormatError("Tiled JSON unsupported layer class")
        # External image paths, custom properties, world event scripts
        # and object metadata do not produce network, filesystem or code IO.
    return project_tiled_map(acc.result(),max_chars=max_chars)
