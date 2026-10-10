"""Bounded deterministic 2D geometry for original homebrew game worlds."""
from __future__ import annotations
from collections import deque
from fractions import Fraction
from heapq import heappop, heappush

class GeometryError(ValueError):
    """Malformed geometry or exceeding constrained device budgets."""

def _int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GeometryError(f"invalid {name}")
    return value

def _point(value: object) -> tuple[int,int]:
    if not isinstance(value,(tuple,list)) or len(value)!=2:
        raise GeometryError("point requires two bounded coordinates")
    return _int(value[0],"x",0,63),_int(value[1],"y",0,63)

def _grid(rows: object) -> tuple[str,...]:
    if (not isinstance(rows,(tuple,list)) or not 1<=len(rows)<=64
            or any(not isinstance(row,str) or not 1<=len(row)<=64
                   or set(row)-set("#.SGCH") for row in rows)
            or any(len(row)!=len(rows[0]) for row in rows)):
        raise GeometryError("grid must be canonical, rectangular and within 64x64")
    return tuple(rows)

def _rect(rect: object) -> tuple[int,int,int,int]:
    if not isinstance(rect,(tuple,list)) or len(rect)!=4:
        raise GeometryError("rectangle requires (x,y,width,height)")
    x,y,w,h=rect
    return (_int(x,"rect x",-32768,32767),_int(y,"rect y",-32768,32767),
            _int(w,"rect width",1,2048),_int(h,"rect height",1,2048))

def walkable_tile_neighbors(rows: object, position: object) -> tuple[tuple[int,int],...]:
    """Canonical four-direction adjacency excluding walls and map escapes."""
    grid=_grid(rows)
    x,y=_point(position)
    if y>=len(grid) or x>=len(grid[0]) or grid[y][x]=="#":
        raise GeometryError("start tile must be within non-wall map")
    candidates=((x,y-1),(x-1,y),(x+1,y),(x,y+1))
    return tuple((cx,cy) for cx,cy in candidates
                 if 0<=cy<len(grid) and 0<=cx<len(grid[0])
                 and grid[cy][cx]!="#")
