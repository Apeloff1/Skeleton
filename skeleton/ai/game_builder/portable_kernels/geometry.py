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

def astar_path(rows: object, origin: object, destination: object) -> tuple[tuple[int,int],...]:
    """Optimal grid path with deterministic tie order and hard map-size cap."""
    grid=_grid(rows)
    start=_point(origin)
    goal=_point(destination)
    width,height=len(grid[0]),len(grid)
    if any(not(0<=x<width and 0<=y<height) or grid[y][x]=="#"
           for x,y in (start,goal)):
        raise GeometryError("A* endpoints must lie on traversable tiles")
    queue=[(abs(start[0]-goal[0])+abs(start[1]-goal[1]),0,start[1],start[0])]
    previous={start:None}
    cost={start:0}
    while queue:
        _,steps,y,x=heappop(queue)
        current=(x,y)
        if steps!=cost[current]:
            continue
        if current==goal:
            reverse=[]
            while current is not None:
                reverse.append(current)
                current=previous[current]
            return tuple(reversed(reverse))
        for nxt in walkable_tile_neighbors(grid,current):
            alternative=steps+1
            if alternative<cost.get(nxt,4097):
                cost[nxt]=alternative
                previous[nxt]=current
                priority=alternative+abs(nxt[0]-goal[0])+abs(nxt[1]-goal[1])
                heappush(queue,(priority,alternative,nxt[1],nxt[0]))
    return ()

def rect_intersects(first: object, second: object) -> bool:
    """Half-open AABB collision; edge contact alone is never penetration."""
    ax,ay,aw,ah=_rect(first)
    bx,by,bw,bh=_rect(second)
    return ax<bx+bw and bx<ax+aw and ay<by+bh and by<ay+ah

def swept_aabb_hit(moving: object, obstacle: object, dx: int,
                   dy: int) -> Fraction | None:
    """First exact time-of-impact on [0,1] for two bounded rectangles.

    Rational slab calculations avoid non-deterministic float rounding across
    CPUs. Stationary separated axes cannot collide; retreating edge contact
    is not a new hit.
    """
    ax,ay,aw,ah=_rect(moving)
    bx,by,bw,bh=_rect(obstacle)
    vx=_int(dx,"frame delta x",-2048,2048)
    vy=_int(dy,"frame delta y",-2048,2048)
    if rect_intersects(moving,obstacle):
        return Fraction(0)
    start=[]
    stop=[]
    for left,size,target,target_size,delta in (
        (ax,aw,bx,bw,vx),(ay,ah,by,bh,vy)
    ):
        if delta==0:
            if left>=target+target_size or target>=left+size:
                return None
            start.append(Fraction(-1))
            stop.append(Fraction(2))
        elif delta>0:
            start.append(Fraction(target-(left+size),delta))
            stop.append(Fraction(target+target_size-left,delta))
        else:
            start.append(Fraction(target+target_size-left,delta))
            stop.append(Fraction(target-(left+size),delta))
    entry=max(Fraction(0),*start)
    departure=min(Fraction(1),*stop)
    if entry>departure or departure<=0:
        return None
    return entry

def shelf_pack_rectangles(sizes: object, atlas_width: int) -> tuple[tuple[int,int,int,int],...]:
    """Deterministic bounded shelf packing for original sprite atlases."""
    width=_int(atlas_width,"atlas width",1,2048)
    if not isinstance(sizes,(tuple,list)) or not 1<=len(sizes)<=256:
        raise GeometryError("sprite atlas requires one to 256 tile sizes")
    cursor_x=cursor_y=row_height=0
    placed=[]
    for size in sizes:
        if not isinstance(size,(tuple,list)) or len(size)!=2:
            raise GeometryError("sprite size requires width and height")
        w=_int(size[0],"sprite width",1,512)
        h=_int(size[1],"sprite height",1,512)
        if w>width:
            raise GeometryError("sprite exceeds atlas row width")
        if cursor_x+w>width:
            cursor_y+=row_height
            cursor_x=row_height=0
        if cursor_y+h>2048:
            raise GeometryError("sprite atlas exceeds 2048-pixel height budget")
        placed.append((cursor_x,cursor_y,w,h))
        cursor_x+=w
        row_height=max(row_height,h)
    return tuple(placed)

def camera_clamp(center: object, world_size: object,
                 viewport_size: object) -> tuple[int,int]:
    """Clamp a 2D camera to the original world's actual scrollable extent."""
    def dimension_pair(value: object, label: str, low: int, high: int) -> tuple[int,int]:
        if not isinstance(value,(tuple,list)) or len(value)!=2:
            raise GeometryError(f"{label} must contain two dimensions")
        return (_int(value[0],label+" width",low,high),
                _int(value[1],label+" height",low,high))
    world_w,world_h=dimension_pair(world_size,"world",1,65535)
    view_w,view_h=dimension_pair(viewport_size,"viewport",1,4096)
    x,y=dimension_pair(center,"camera center",0,65535)
    if x>=world_w or y>=world_h:
        raise GeometryError("camera center outside source world")
    return (min(max(0,x-view_w//2),max(0,world_w-view_w)),
            min(max(0,y-view_h//2),max(0,world_h-view_h)))
