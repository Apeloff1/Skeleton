"""Generated native Godot directed labyrinth map with canonical route overlays.

Pure authored-world visualization; clicking a node merely *requests* a route.
It never changes quests, performs travel or confers player permissions.
"""
from __future__ import annotations

MAP_SCRIPT = r'''extends Control

signal node_selected(key: String)

var nodes: Dictionary = {}
var graph: Dictionary = {}
var authored_passages: Array = []
var blocked_foot_links: Array = []
var live_transport_permissions: Dictionary = {}
var selected_steps: Array = []
var ordered_nodes: Array[String] = []
var now: String = ""
var selected_path: Array = []
var cursor_target: String = ""
var node_radius: float = 7.0
var map_scale: float = 1.0

func _ready() -> void:
    custom_minimum_size = Vector2(400, 185)
    mouse_filter = Control.MOUSE_FILTER_STOP
    resized.connect(_rebuild)
    queue_redraw()

func set_world(world: Dictionary) -> void:
    nodes.clear()
    graph.clear()
    ordered_nodes.clear()
    for record in world.get("scenes", []):
        var key: String = str(record.get("key", ""))
        if not key.is_empty() and not nodes.has(key):
            nodes[key] = {
                "key": key,
                "title": str(record.get("title", "")),
                "region": str(record.get("region", "")),
                "links": record.get("links", []).duplicate(),
            }
            ordered_nodes.append(key)
    ordered_nodes.sort()
    authored_passages.clear()
    var dynamics: Dictionary = world.get("dynamics", {})
    for record in dynamics.get("passages", []):
        if record is Dictionary:
            authored_passages.append(record)
    _rebuild()

func blocked_routes(blocked: Array) -> void:
    blocked_foot_links = blocked.duplicate(true)
    queue_redraw()


func update_transport_options(options: Array) -> void:
    live_transport_permissions.clear()
    for option in options:
        if option is Dictionary:
            live_transport_permissions[str(option.get("key", ""))] = option.get(
                "available", false) == true
    queue_redraw()


func highlight(scene: String, route: Array = [], steps: Array = []) -> void:
    now = scene
    selected_path = route.duplicate()
    selected_steps = steps.duplicate(true)
    queue_redraw()

func _rebuild() -> void:
    if ordered_nodes.is_empty():
        queue_redraw()
        return
    graph.clear()
    var regions: Array[String] = []
    for name in ordered_nodes:
        var region: String = str(nodes[name].get("region", ""))
        if not regions.has(region):
            regions.append(region)
    regions.sort()
    var columns: int = maxi(1, mini(6, regions.size()))
    var width_each: float = maxf(1.0, size.x - 20.0) / float(columns)
    var region_index: Dictionary = {}
    var population: Dictionary = {}
    for i in range(regions.size()):
        region_index[regions[i]] = i
        population[regions[i]] = 0
    for name in ordered_nodes:
        var region: String = str(nodes[name].get("region", ""))
        population[region] = int(population[region]) + 1
    var ordinal: Dictionary = {}
    for name in ordered_nodes:
        var region: String = str(nodes[name].get("region", ""))
        var index: int = int(ordinal.get(region, 0))
        ordinal[region] = index + 1
        var col: int = int(region_index[region]) % columns
        var row_group: int = int(int(region_index[region]) / columns)
        var column_count: int = int(population[region])
        var row_span: float = maxf(26.0, size.y / float(maxi(column_count, 1) + 1))
        var x: float = 10.0 + (float(col) + 0.5) * width_each
        var y: float = 16.0 + (float(index) + 1.0) * row_span + float(row_group) * 7.0
        graph[name] = Vector2(x, minf(y, size.y - 12.0))
    queue_redraw()

func _edge(a: Vector2, b: Vector2, selected: bool) -> void:
    var color = Color(0.96, 0.78, 0.22, 0.95) if selected else Color(0.39, 0.49, 0.58, 0.5)
    draw_line(a, b, color, 2.4 if selected else 1.0)
    var vector: Vector2 = b - a
    if vector.length() >= 16.0:
        var unit: Vector2 = vector.normalized()
        var point: Vector2 = b - unit * (node_radius + 2.0)
        var wing: Vector2 = Vector2(-unit.y, unit.x) * 3.0
        draw_line(point - unit * 7.0 + wing, point, color, 1.5)
        draw_line(point - unit * 7.0 - wing, point, color, 1.5)

func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, size), Color(0.035, 0.065, 0.1, 0.97))
    for name in ordered_nodes:
        if not graph.has(name):
            continue
        var src: Vector2 = graph[name]
        for next in nodes[name].get("links", []):
            if not graph.has(next):
                continue
            var linked: bool = false
            for i in range(selected_path.size() - 1):
                if selected_path[i] == name and selected_path[i + 1] == next:
                    linked = true
                    break
            _edge(src, graph[next], linked)
    # World passages are labeled transit routes, visually distinct from
    # walkable graph edges. They remain locked unless the Python engine offers
    # an actual action; clicking a node does not override its permission.
    for passage in authored_passages:
        var a: String = str(passage.get("source", ""))
        var b: String = str(passage.get("destination", ""))
        if graph.has(a) and graph.has(b):
            var key: String = str(passage.get("key", ""))
            var selected: bool = false
            for choice in selected_steps:
                if choice is Dictionary and choice.get("transport_key") == key:
                    selected = true
                    break
            var available: bool = live_transport_permissions.get(key, false) == true
            var color = (Color(0.96, 0.77, 0.22, 0.99) if selected else
                Color(0.29, 0.90, 0.52, 0.89) if available else
                Color(0.73, 0.33, 0.93, 0.70))
            draw_dashed_line(graph[a], graph[b], color,
                             3.0 if selected else 1.4, 6.0)
            if passage.get("bidirectional", false) != true:
                draw_circle(graph[b], 2.0, color)
    for blocked in blocked_foot_links:
        var a: String = str(blocked.get("source", now))
        var b: String = str(blocked.get("destination", ""))
        if graph.has(a) and graph.has(b):
            draw_line(graph[a], graph[b], Color(0.93, 0.23, 0.16, 0.80), 2.0)
    for name in ordered_nodes:
        if not graph.has(name):
            continue
        var point: Vector2 = graph[name]
        var active: bool = name == now
        var chosen: bool = name == cursor_target
        var on_route: bool = selected_path.has(name)
        var fill = Color(0.22, 0.9, 0.49) if active else (
            Color(1.0, 0.74, 0.2) if on_route else Color(0.30, 0.55, 0.83))
        draw_circle(point, node_radius + (3.0 if active or chosen else 0.0), fill)
        if chosen:
            draw_arc(point, node_radius + 7.0, 0.0, TAU, 24, Color.WHITE, 1.5)
        if get_theme_default_font() != null and (
                active or chosen or ordered_nodes.size() <= 20):
            draw_string(get_theme_default_font(), point + Vector2(11.0, -2.0),
                        name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.WHITE)

func _gui_input(event: InputEvent) -> void:
    if not (event is InputEventMouseButton):
        return
    var click: InputEventMouseButton = event
    if not click.pressed or click.button_index != MOUSE_BUTTON_LEFT:
        return
    var target: String = ""
    var distance: float = 22.0
    for key in ordered_nodes:
        var measured: float = click.position.distance_to(graph.get(key, Vector2(-10000, -10000)))
        if measured < distance:
            distance = measured
            target = key
    if not target.is_empty():
        cursor_target = target
        queue_redraw()
        node_selected.emit(target)
        accept_event()
'''
