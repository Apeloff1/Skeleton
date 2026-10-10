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

def bresenham_line(start: object, end: object) -> tuple[tuple[int,int],...]:
    """Integer raster ray for tile visibility, lasers and grid interaction."""
    x0,y0=_point(start)
    x1,y1=_point(end)
    dx=abs(x1-x0)
    dy=-abs(y1-y0)
    step_x=1 if x0<x1 else -1
    step_y=1 if y0<y1 else -1
    error=dx+dy
    points=[]
    while True:
        points.append((x0,y0))
        if (x0,y0)==(x1,y1):
            return tuple(points)
        twice=2*error
        if twice>=dy:
            error+=dy
            x0+=step_x
        if twice<=dx:
            error+=dx
            y0+=step_y

def line_of_sight(rows: object, start: object, target: object) -> bool:
    """Grid ray visibility that never sees through walls or off-map tiles."""
    grid=_grid(rows)
    a=_point(start)
    b=_point(target)
    width,height=len(grid[0]),len(grid)
    if any(not (0<=x<width and 0<=y<height) for x,y in (a,b)):
        raise GeometryError("ray origin or target outside map")
    if grid[a[1]][a[0]]=="#":
        raise GeometryError("ray starts inside opaque wall")
    return all(grid[y][x]!="#" for x,y in bresenham_line(a,b)[1:])

def flood_fill(rows: object, origin: object) -> tuple[tuple[int,int],...]:
    """Bounded flood fill for validating accessible levels and spawn islands."""
    grid=_grid(rows)
    start=_point(origin)
    if start[1]>=len(grid) or start[0]>=len(grid[0]) or grid[start[1]][start[0]]=="#":
        raise GeometryError("flood origin must be traversable")
    seen={start}
    queue=deque((start,))
    while queue:
        current=queue.popleft()
        for neighbor in walkable_tile_neighbors(grid,current):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return tuple(sorted(seen,key=lambda point:(point[1],point[0])))

def distance_field(rows: object, origin: object) -> tuple[tuple[int,...],...]:
    """Exact breadth-first traversal distance, with -1 for walls/unreachable."""
    grid=_grid(rows)
    start=_point(origin)
    if start[1]>=len(grid) or start[0]>=len(grid[0]) or grid[start[1]][start[0]]=="#":
        raise GeometryError("distance source must be traversable")
    costs=[[-1 for _ in row] for row in grid]
    costs[start[1]][start[0]]=0
    queue=deque((start,))
    while queue:
        x,y=queue.popleft()
        for nx,ny in walkable_tile_neighbors(grid,(x,y)):
            if costs[ny][nx]==-1:
                costs[ny][nx]=costs[y][x]+1
                queue.append((nx,ny))
    return tuple(tuple(row) for row in costs)
