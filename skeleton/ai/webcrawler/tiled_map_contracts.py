"""Finite source-side Tiled map/tileset metric kernel, never a world renderer.

All tile IDs and map objects are external unreviewed source statements.
The kernel processes inert scalar tile ID arrays only; no game event,
embedded script, image/tileset source, collision behavior, or generated
world is loaded. Tile flip bits are counted, not used for rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .research_projection import ResearchFormatError,ResearchProjection,project_lines

_MAX_LAYERS=256
_MAX_CELLS=65536
_MAX_OBJECTS=2048
_MAX_TILESETS=128
_MAX_CHUNKS=256
_FLIP_BITS=0xE0000000
_GID_MASK=0x1FFFFFFF


@dataclass(frozen=True)
class TiledMapMetrics:
    kind:str
    tile_width:int
    tile_height:int
    width:int
    height:int
    infinite:bool
    layers:int
    tilesets:int
    objects:int
    chunks:int
    cells:int
    occupied_cells:int
    flipped_cells:int
    image_layers:int
    max_gid:int
    from_external_unreviewed_source:bool=True
    source_references_opened:bool=False
    game_engine_executed:bool=False


class TiledAccumulator:
    def __init__(
        self,*,tile_width:int,tile_height:int,width:int,height:int,
        infinite:bool,kind:str="Tiled map",
    ):
        for name,value,minimum,maximum in (
            ("tile width",tile_width,1,1024),
            ("tile height",tile_height,1,1024),
            ("map width",width,0,65536),
            ("map height",height,0,65536),
        ):
            if type(value) is not int or not minimum<=value<=maximum:
                raise ResearchFormatError("Tiled "+name+" outside finite capacity")
        if type(infinite) is not bool or not isinstance(kind,str) or len(kind)>128:
            raise ResearchFormatError("invalid Tiled source mode")
        if not infinite and (width<1 or height<1 or width*height>_MAX_CELLS):
            raise ResearchFormatError("finite Tiled map dimensions exceed cell bound")
        self.kind=kind
        self.tile_width=tile_width
        self.tile_height=tile_height
        self.width=width
        self.height=height
        self.infinite=infinite
        self.layers=0
        self.tilesets=0
        self.objects=0
        self.chunks=0
        self.cells=0
        self.occupied=0
        self.flipped=0
        self.image_layers=0
        self.max_gid=0

    def layer(self)->None:
        self.layers+=1
        if self.layers>_MAX_LAYERS:
            raise ResearchFormatError("Tiled scene layer capacity exceeded")

    def tileset(self)->None:
        self.tilesets+=1
        if self.tilesets>_MAX_TILESETS:
            raise ResearchFormatError("Tiled tileset references exceed capacity")

    def image_layer(self)->None:
        self.layer()
        self.image_layers+=1

    def objects_add(self,n:int)->None:
        if type(n) is not int or n<0 or self.objects+n>_MAX_OBJECTS:
            raise ResearchFormatError("Tiled object capacity exceeded")
        self.objects+=n

    def chunk(self,x:int,y:int)->None:
        if (type(x) is not int or type(y) is not int or
                not -1_000_000<=x<=1_000_000
                or not -1_000_000<=y<=1_000_000):
            raise ResearchFormatError("Tiled chunk coordinate outside limits")
        self.chunks+=1
        if self.chunks>_MAX_CHUNKS:
            raise ResearchFormatError("Tiled map chunk capacity exceeded")

    def tile_data(self,values:list[int],*,width:int,height:int)->None:
        if (type(width) is not int or type(height) is not int
                or width<1 or height<1 or width*height>_MAX_CELLS
                or not isinstance(values,list) or len(values)!=width*height
                or self.cells+len(values)>_MAX_CELLS):
            raise ResearchFormatError("Tiled declared tile matrix capacity mismatch")
        occupied=flipped=0
        for value in values:
            if type(value) is not int or not 0<=value<=0xFFFFFFFF:
                raise ResearchFormatError("Tiled GID outside uint32")
            gid=value&_GID_MASK
            occupied+=int(gid!=0)
            flipped+=int(bool(value&_FLIP_BITS))
            self.max_gid=max(self.max_gid,gid)
        self.cells+=len(values)
        self.occupied+=occupied
        self.flipped+=flipped

    def result(self)->TiledMapMetrics:
        if self.layers<1:
            raise ResearchFormatError("Tiled map has no source-declared layers")
        return TiledMapMetrics(
            kind=self.kind,tile_width=self.tile_width,tile_height=self.tile_height,
            width=self.width,height=self.height,infinite=self.infinite,
            layers=self.layers,tilesets=self.tilesets,objects=self.objects,
            chunks=self.chunks,cells=self.cells,occupied_cells=self.occupied,
            flipped_cells=self.flipped,image_layers=self.image_layers,
            max_gid=self.max_gid,
        )


def project_tiled_map(
    data:TiledMapMetrics,*,max_chars:int,
)->ResearchProjection:
    if not isinstance(data,TiledMapMetrics):
        raise ResearchFormatError("Tiled map requires typed bounded metrics")
    lines=[
        f"Game map source format: {data.kind}; infinite: {data.infinite}",
        f"Tile dimensions: {data.tile_width} x {data.tile_height}; "
        f"map cells: {data.width} x {data.height}",
        f"Layers: {data.layers}; image layers: {data.image_layers}; "
        f"external tileset declarations: {data.tilesets}",
        f"Objects declared: {data.objects}; chunks declared: {data.chunks}",
        f"Finite tile IDs: {data.cells}; occupied cells: {data.occupied_cells}; "
        f"flipped/rotated flags: {data.flipped_cells}",
        f"Maximum declared GID: {data.max_gid}",
        "Tileset/media paths, objects, scripts, physics and world execution: not loaded",
    ]
    return project_lines(lines,title=data.kind+" source",max_chars=max_chars)
