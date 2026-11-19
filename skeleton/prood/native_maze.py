"""Compile a receipt-verified design variant into a standalone Godot maze.

The source manifest qualifies emitted text only. Native engine provenance,
boot, input and graphics qualification remain independent.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json

from skeleton.forge.source_manifest import source_manifest
from skeleton.prood.design_campaign import collect_package
from skeleton.prood.design_contract import DesignRequest
from skeleton.prood.mechanics_design import maze_distance


@dataclass(frozen=True, slots=True)
class NativeMazeSource:
    package_digest: str
    variant: int
    files: dict[str, str]
    manifest: dict
    native_verified: bool = False


def _shortest_path(maze):
    maze_distance(maze)
    rows=maze["rows"]
    start,end=tuple(maze["entry"]),tuple(maze["exit"])
    parents={start:None}
    queue=deque([start])
    while queue:
        here=queue.popleft()
        if here==end:
            route=[]
            while here is not None:
                route.append(here)
                here=parents[here]
            return list(reversed(route))
        x,y=here
        for dx,dy in ((1,0),(0,1),(-1,0),(0,-1)):
            point=(x+dx,y+dy)
            i,j=point
            if (0<=j<len(rows) and 0<=i<len(rows[j]) and rows[j][i]=="."
                    and point not in parents):
                parents[point]=here
                queue.append(point)
    raise ValueError("verified maze has no route")


def _objective_data(maze, quest, economy):
    route=_shortest_path(maze)
    count=min(len(route)-2,len(quest["steps"]))
    if count<1:
        raise ValueError("no reachable interior objective tiles")
    selected=[route[1+(index*(len(route)-2))//count] for index in range(count)]
    if len(set(selected))!=count:
        raise ValueError("objective coordinate collision")
    rewards=[]
    for index,point in enumerate(selected):
        row=economy["steps"][index]
        rewards.append({"position":list(point),"reward":row["income"],
                        "label":quest["steps"][index]["objective"]})
    return rewards


_PROJECT = """; Generated original source. No external assets or autoloads.
config_version=5

[application]
config/name="Prood Original Maze"
run/main_scene="res://main.tscn"

[display]
window/size/viewport_width=960
window/size/viewport_height=780
window/stretch/mode="canvas_items"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""

_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]

[node name="Maze" type="Node2D"]
script = ExtResource("1")
"""

_SCRIPT = r'''extends Node2D

const COMPLETE_MARKER = "PROOD_MAZE_COMPLETE"
const FAILED_MARKER = "PROOD_MAZE_FAILED"
const DIRECTIONS = [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
var cells: Array = []
var palette: Array = []
var tokens: Dictionary = {}
var player := Vector2i.ZERO
var destination := Vector2i.ZERO
var score := 0
var required := 0
var collected := 0
var moves := 0
var won := false
var valid := false
var touch_start := Vector2.ZERO
var message := "Collect every objective, then reach the exit."

func _ready() -> void:
    var raw = FileAccess.get_file_as_string("res://design.json")
    var parsed = JSON.parse_string(raw)
    if not parsed is Dictionary:
        _fail("invalid design data")
        return
    var data: Dictionary = parsed
    cells = data["maze"]["rows"]
    palette = data["palette"]
    player = _point(data["maze"]["entry"])
    destination = _point(data["maze"]["exit"])
    for item in data["objectives"]:
        var p := _point(item["position"])
        if tokens.has(p) or not _walkable(p):
            _fail("invalid objective")
            return
        tokens[p] = int(item["reward"])
    required = tokens.size()
    if not _walkable(player) or not _walkable(destination) or required < 1:
        _fail("invalid maze endpoints")
        return
    valid = true
    get_viewport().size_changed.connect(queue_redraw)
    queue_redraw()
    if "--prood-maze-selftest" in OS.get_cmdline_user_args():
        call_deferred("_selftest")

func _point(value: Array) -> Vector2i:
    return Vector2i(int(value[0]), int(value[1]))

func _walkable(p: Vector2i) -> bool:
    return p.y >= 0 and p.y < cells.size() and p.x >= 0 and p.x < cells[p.y].length() and cells[p.y][p.x] == "."

func _fail(reason: String) -> void:
    message = reason
    valid = false
    queue_redraw()
    if "--prood-maze-selftest" in OS.get_cmdline_user_args():
        print(FAILED_MARKER + " " + reason)
        get_tree().quit(1)

func _move(delta: Vector2i) -> bool:
    if not valid or won or delta not in DIRECTIONS:
        return false
    var next := player + delta
    if not _walkable(next):
        return false
    player = next
    moves += 1
    if tokens.has(player):
        score += int(tokens[player])
        collected += 1
        tokens.erase(player)
        message = "Objective recovered."
    if player == destination:
        if tokens.is_empty():
            won = true
            message = "Maze complete!"
        else:
            message = "Exit locked until remaining objectives are recovered."
    queue_redraw()
    return true

func _unhandled_input(event: InputEvent) -> void:
    if not valid or won:
        return
    for pair in [["ui_up", Vector2i(0,-1)], ["ui_down", Vector2i(0,1)], ["ui_left", Vector2i(-1,0)], ["ui_right", Vector2i(1,0)]]:
        if event.is_action_pressed(pair[0]):
            _move(pair[1])
            get_viewport().set_input_as_handled()
            return
    if event is InputEventScreenTouch:
        if event.pressed:
            touch_start = event.position
        else:
            var drag: Vector2 = event.position - touch_start
            if drag.length() >= 24.0:
                if absf(drag.x) >= absf(drag.y):
                    _move(Vector2i(1 if drag.x > 0 else -1, 0))
                else:
                    _move(Vector2i(0, 1 if drag.y > 0 else -1))
                get_viewport().set_input_as_handled()

func _draw() -> void:
    var font = ThemeDB.fallback_font
    var view := get_viewport_rect().size
    draw_rect(Rect2(Vector2.ZERO,view),Color("#12141C"))
    if not valid:
        draw_string(font,Vector2(24,45),message)
        return
    var size: float = floorf(minf((view.x-48.0)/float(cells[0].length()),(view.y-120.0)/float(cells.size())))
    if size < 1.0:
        return
    var origin := Vector2((view.x-size*cells[0].length())/2.0,66.0)
    for y in range(cells.size()):
        for x in range(cells[y].length()):
            var p := Vector2i(x,y)
            var tone := Color(palette[0] if cells[y][x] == "#" else palette[1])
            if p == destination:
                tone = Color(palette[3] if tokens.is_empty() else palette[2])
            draw_rect(Rect2(origin+Vector2(p)*size,Vector2(size-1,size-1)),tone)
            if tokens.has(p):
                draw_circle(origin+(Vector2(p)+Vector2(0.5,0.5))*size,size*0.24,Color(palette[3]))
    draw_circle(origin+(Vector2(player)+Vector2(0.5,0.5))*size,size*0.33,Color.WHITE)
    draw_string(font,Vector2(24,30),"OBJECTIVES %d / %d    SALVAGE %d    MOVES %d" % [collected,required,score,moves],HORIZONTAL_ALIGNMENT_LEFT,-1,20)
    draw_string(font,Vector2(24,view.y-24),message,HORIZONTAL_ALIGNMENT_LEFT,-1,16)

func _path(start: Vector2i, goal: Vector2i) -> Array:
    var queue: Array[Vector2i] = [start]
    var previous: Dictionary = {}
    previous[start] = start
    var cursor := 0
    while cursor < queue.size():
        var p: Vector2i = queue[cursor]
        cursor += 1
        if p == goal:
            var path: Array[Vector2i] = []
            while p != start:
                path.push_front(p)
                p = previous[p]
            return path
        for delta in DIRECTIONS:
            var next: Vector2i = p + delta
            if _walkable(next) and not previous.has(next):
                previous[next] = p
                queue.append(next)
    return []

func _travel(goal: Vector2i) -> bool:
    if player == goal:
        return true
    var route := _path(player,goal)
    if route.is_empty():
        return false
    for point in route:
        if not _move(point-player):
            return false
    return player == goal

func _selftest() -> void:
    # Exercise the production movement/collection/locked-exit code, not a
    # synthetic marker. Engine provenance is qualified outside this project.
    var goals := tokens.keys()
    for point in goals:
        if tokens.has(point) and not _travel(point):
            _fail("objective unreachable")
            return
    if not _travel(destination) or not won or collected != required:
        _fail("completion condition missing")
        return
    print(COMPLETE_MARKER + " objectives=%d salvage=%d moves=%d" % [collected,score,moves])
    get_tree().quit(0)
'''


def export_native_maze(journal, results, request: DesignRequest, *, variant: int) -> NativeMazeSource:
    if type(request) is not DesignRequest or type(variant) is not int or not 1<=variant<=request.variants:
        raise ValueError("invalid verified design variant")
    package=collect_package(journal,results,request)
    prefix=f"variants/{variant:02d}/"
    extract=lambda name:json.loads(package.files[prefix+name+".json"])
    maze,quest,economy,tiles=(extract(name) for name in ("maze","quest","economy","tiles"))
    data={"schema":"prood.native-maze.v1","package_digest":package.package_digest,
          "maze":maze,"palette":tiles["palette"],"objectives":_objective_data(maze,quest,economy)}
    files={"project.godot":_PROJECT,"main.tscn":_SCENE,"main.gd":_SCRIPT,
           "design.json":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n"}
    manifest=source_manifest(files)
    return NativeMazeSource(package.package_digest,variant,files,manifest)
