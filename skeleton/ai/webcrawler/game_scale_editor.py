"""Real editable scene tools with undo/redo: capabilities 071–080.

Every scene mutation preserves exactly one start, one goal and a traversable
path. Edits are immutable and can be replayed in deterministic history.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass,replace
from hashlib import sha256
import json

from .game_knowledge_design import GameBlueprint,find_level_route

@dataclass(frozen=True)
class EditorHistory:
    versions:tuple[GameBlueprint,...]
    cursor:int

_ALLOWED=frozenset("#.PCGE^")
def _grid(bp:GameBlueprint):return [list(row) for row in bp.grid]

def _finish(bp:GameBlueprint,rows:list[list[str]])->GameBlueprint:
    if len(rows)!=bp.height or any(len(row)!=bp.width for row in rows):
        raise ValueError("invalid scene dimensions")
    if any(t not in _ALLOWED for row in rows for t in row):
        raise ValueError("unsupported scene tile")
    if sum(row.count("P") for row in rows)!=1 or sum(row.count("G") for row in rows)!=1:
        raise ValueError("scene needs one player and exit")
    lines=tuple("".join(row) for row in rows)
    if not find_level_route(lines):
        raise ValueError("scene edit disconnected player from exit")
    digest=sha256(json.dumps(
        [bp.fingerprint,lines],separators=(",",":"),
    ).encode()).hexdigest()
    return replace(bp,grid=lines,fingerprint=digest)

def _inside(bp:GameBlueprint,x:int,y:int):
    if not 0<=x<bp.width or not 0<=y<bp.height:
        raise ValueError("editor point outside level")

def open_editor_history(bp:GameBlueprint)->EditorHistory:
    return EditorHistory((bp,),0)

def record_editor_edit(history:EditorHistory,next_scene:GameBlueprint,
                       *,max_depth:int=100)->EditorHistory:
    if not 1<=max_depth<=1000:raise ValueError("invalid undo history")
    versions=(history.versions[:history.cursor+1]+(next_scene,))[-max_depth:]
    return EditorHistory(versions,len(versions)-1)

# 071 Brush a single tile while preserving the scene's structural semantics.
def paint_scene_tile(bp:GameBlueprint,x:int,y:int,tile:str)->GameBlueprint:
    _inside(bp,x,y)
    if tile not in _ALLOWED or tile in "PG":
        raise ValueError("use dedicated spawn/goal move tools")
    rows=_grid(bp)
    if rows[y][x] in "PG":raise ValueError("cannot erase spawn/goal")
    rows[y][x]=tile
    return _finish(bp,rows)

# 072 Paint a disk of terrain, collectibles or hazards with a real radius.
def paint_scene_brush(bp:GameBlueprint,x:int,y:int,tile:str, *,
                      radius:int=2)->GameBlueprint:
    _inside(bp,x,y)
    if tile not in _ALLOWED or tile in "PG" or not 1<=radius<=16:
        raise ValueError("invalid scene brush")
    rows=_grid(bp)
    for ty in range(max(0,y-radius),min(bp.height,y+radius+1)):
        for tx in range(max(0,x-radius),min(bp.width,x+radius+1)):
            if (tx-x)**2+(ty-y)**2<=radius**2 and rows[ty][tx] not in "PG":
                rows[ty][tx]=tile
    return _finish(bp,rows)

# 073 Proper bounded connected-component flood fill.
def flood_scene_region(bp:GameBlueprint,x:int,y:int,tile:str, *,
                       max_tiles:int=4096)->GameBlueprint:
    _inside(bp,x,y)
    if tile not in _ALLOWED or tile in "PG" or not 1<=max_tiles<=100000:
        raise ValueError("invalid fill request")
    rows=_grid(bp);original=rows[y][x]
    if original in "PG":raise ValueError("cannot replace scene origin/exit")
    if original==tile:return bp
    q=deque([(x,y)]);seen={(x,y)}
    while q:
        cx,cy=q.popleft()
        rows[cy][cx]=tile
        for nx,ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)):
            if 0<=nx<bp.width and 0<=ny<bp.height and rows[ny][nx]==original and (nx,ny) not in seen:
                if len(seen)>=max_tiles:raise ValueError("fill budget exceeded")
                seen.add((nx,ny));q.append((nx,ny))
    return _finish(bp,rows)

# 074 Draw an actual solid/fill rectangle or platform outline.
def draw_scene_rectangle(bp:GameBlueprint,x:int,y:int,w:int,h:int, *,
                         tile:str,filled:bool=True)->GameBlueprint:
    if not 1<=w<=128 or not 1<=h<=128 or tile not in _ALLOWED or tile in "PG":
        raise ValueError("invalid level rectangle")
    _inside(bp,x,y);_inside(bp,x+w-1,y+h-1)
    rows=_grid(bp)
    for yy in range(y,y+h):
        for xx in range(x,x+w):
            if filled or xx in (x,x+w-1) or yy in (y,y+h-1):
                if rows[yy][xx] not in "PG":rows[yy][xx]=tile
    return _finish(bp,rows)

# 075 Move the actual player start marker onto walkable space.
def relocate_player_spawn(bp:GameBlueprint,x:int,y:int)->GameBlueprint:
    _inside(bp,x,y)
    rows=_grid(bp)
    if rows[y][x] not in ".C":raise ValueError("spawn target occupied")
    for row in rows:
        for index,t in enumerate(row):
            if t=="P":row[index]="."
    rows[y][x]="P"
    return _finish(bp,rows)

# 076 Move exit goal without leaving a duplicate or unreachable goal.
def relocate_level_exit(bp:GameBlueprint,x:int,y:int)->GameBlueprint:
    _inside(bp,x,y)
    rows=_grid(bp)
    if rows[y][x] not in ".C":raise ValueError("goal target occupied")
    for row in rows:
        for index,t in enumerate(row):
            if t=="G":row[index]="."
    rows[y][x]="G"
    return _finish(bp,rows)

# 077 Copy genuine multicharacter editable map sections.
def copy_scene_region(bp:GameBlueprint,x:int,y:int,w:int,h:int
                      )->tuple[str,...]:
    if not 1<=w<=128 or not 1<=h<=128:
        raise ValueError("invalid clipboard dimensions")
    _inside(bp,x,y);_inside(bp,x+w-1,y+h-1)
    return tuple(row[x:x+w] for row in bp.grid[y:y+h])

# 078 Paste a clipboard stencil without duplicating protected markers.
def paste_scene_region(bp:GameBlueprint,clipboard:tuple[str,...], *,
                       x:int,y:int,transparent:bool=False)->GameBlueprint:
    if not clipboard or len({len(row) for row in clipboard})!=1:
        raise ValueError("invalid level clipboard")
    h,w=len(clipboard),len(clipboard[0])
    _inside(bp,x,y);_inside(bp,x+w-1,y+h-1)
    if any(char not in _ALLOWED for row in clipboard for char in row):
        raise ValueError("unknown pasted tile")
    rows=_grid(bp)
    for yy,line in enumerate(clipboard):
        for xx,tile in enumerate(line):
            if tile in "PG" or rows[y+yy][x+xx] in "PG":continue
            if transparent and tile==".":continue
            rows[y+yy][x+xx]=tile
    return _finish(bp,rows)

# 079 Step backwards in actual immutable edit history.
def undo_scene_edit(history:EditorHistory)->tuple[EditorHistory,GameBlueprint]:
    cursor=max(0,history.cursor-1)
    updated=replace(history,cursor=cursor)
    return updated,updated.versions[cursor]

# 080 Redo a previously undone branch until a new edit invalidates it.
def redo_scene_edit(history:EditorHistory)->tuple[EditorHistory,GameBlueprint]:
    cursor=min(len(history.versions)-1,history.cursor+1)
    updated=replace(history,cursor=cursor)
    return updated,updated.versions[cursor]
