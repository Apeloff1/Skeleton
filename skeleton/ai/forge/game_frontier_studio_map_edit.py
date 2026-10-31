"""Executable immutable map, palette and layer editing for canonical Forge Studio.

Twenty-five distinct editor actions operate on real StudioProject/MapLayer data.
All edits yield a new typed project; they never mutate source snapshots or
register additional ownership, file access, engines or model execution.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from hashlib import sha256
import json
import math
from typing import Any, Mapping

from .game_frontier_studio import MapLayer, StudioError, StudioProject

MAP_ACTIONS = (
    "tile_set", "rect_fill", "line_draw", "ellipse_fill", "flood_fill",
    "replace_tile", "checker_fill", "stamp", "region_paste",
    "shift_layer", "flip_horizontal", "flip_vertical", "rotate_90",
    "layer_add", "layer_remove", "layer_duplicate", "layer_reorder",
    "layer_elevation", "palette_add", "palette_replace", "palette_swap",
    "palette_remove", "layer_resize", "layer_crop", "layer_clear",
)


def _integer(args: Mapping[str, Any], key: str, lo: int, hi: int) -> int:
    value = args.get(key)
    if type(value) is not int or not lo <= value <= hi:
        raise StudioError(f"{key} requires integer in [{lo},{hi}]")
    return value


def _name(args: Mapping[str, Any], key: str) -> str:
    value = args.get(key)
    if type(value) is not str or not 1 <= len(value) <= 128 or not (
            value[0].isalpha() and all(c.isalnum() or c in "_.:-" for c in value)):
        raise StudioError(f"{key} requires stable bounded identity")
    return value


def _tile(layer: MapLayer, args: Mapping[str, Any], key: str = "tile") -> int:
    return _integer(args, key, -1, len(layer.palette) - 1)


def _xy(layer: MapLayer, args: Mapping[str, Any]) -> tuple[int, int]:
    return (_integer(args, "x", 0, layer.width - 1),
            _integer(args, "y", 0, layer.height - 1))


def _width_height(args: Mapping[str, Any]) -> tuple[int, int]:
    return _integer(args, "width", 1, 256), _integer(args, "height", 1, 256)


def _inside(layer: MapLayer, x: int, y: int) -> int:
    if not 0 <= x < layer.width or not 0 <= y < layer.height:
        raise StudioError("authored coordinate escapes tile layer")
    return y * layer.width + x


def _tile_grid(layer: MapLayer) -> list[list[int]]:
    return [list(layer.data[y * layer.width:(y + 1) * layer.width])
            for y in range(layer.height)]


def _layer(project: StudioProject, args: Mapping[str, Any]) -> tuple[int, MapLayer]:
    name = _name(args, "layer")
    for index, layer in enumerate(project.layers):
        if layer.layer_id == name:
            return index, layer
    raise StudioError("selected layer does not exist")


def _replace_layer(project: StudioProject, index: int, layer: MapLayer) -> StudioProject:
    layers = list(project.layers)
    layers[index] = layer
    return replace(project, layers=tuple(layers))


def _patch_cells(layer: MapLayer, updates: Mapping[int, int]) -> MapLayer:
    data = list(layer.data)
    for index, tile in updates.items():
        if not 0 <= index < len(data) or type(tile) is not int or not -1 <= tile < len(layer.palette):
            raise StudioError("tile operation writes invalid cell or palette index")
        data[index] = tile
    return replace(layer, data=tuple(data))


def _rectangle(layer: MapLayer, args: Mapping[str, Any]) -> tuple[int, int, int, int]:
    x, y = _xy(layer, args)
    width = _integer(args, "width", 1, layer.width)
    height = _integer(args, "height", 1, layer.height)
    if x + width > layer.width or y + height > layer.height:
        raise StudioError("rectangle escapes map bounds")
    return x, y, width, height


def edit_map(project: StudioProject, action: str, args: Mapping[str, Any]) -> StudioProject:
    """Execute a bounded map operation; caller controls project ownership."""
    if type(project) is not StudioProject or action not in MAP_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("unknown map operation or invalid Forge Studio source")
    if action == "layer_add":
        name = _name(args, "layer")
        width, height = _width_height(args)
        raw = args.get("palette")
        if (type(raw) is not list or not 1 <= len(raw) <= 256
                or any(type(v) is not str or not 1 <= len(v) <= 128 for v in raw)):
            raise StudioError("new layer requires bounded string palette")
        if any(layer.layer_id == name for layer in project.layers):
            raise StudioError("duplicate layer identity")
        fill = _integer(args, "fill", -1, len(raw) - 1)
        return replace(project, layers=project.layers + (
            MapLayer(name, width, height, tuple(raw), (fill,) * (width * height)),))
    index, layer = _layer(project, args)
    data = list(layer.data)
    if action == "layer_remove":
        if len(project.layers) == 1:
            raise StudioError("Studio must retain a map layer")
        return replace(project, layers=project.layers[:index] + project.layers[index + 1:])
    if action == "layer_duplicate":
        new = _name(args, "new_layer")
        if any(l.layer_id == new for l in project.layers):
            raise StudioError("duplicate layer")
        return replace(project, layers=project.layers[:index + 1] + (
            replace(layer, layer_id=new),) + project.layers[index + 1:])
    if action == "layer_reorder":
        position = _integer(args, "position", 0, len(project.layers) - 1)
        layers = list(project.layers)
        moved = layers.pop(index)
        layers.insert(position, moved)
        return replace(project, layers=tuple(layers))
    if action == "layer_elevation":
        altitude = args.get("elevation_m")
        if type(altitude) not in (int, float) or not math.isfinite(altitude) or abs(altitude) > 1e5:
            raise StudioError("invalid authored elevation")
        return _replace_layer(project, index, replace(layer, elevation_m=float(altitude)))
    if action == "palette_add":
        name = _name(args, "value")
        if name in layer.palette or len(layer.palette) >= 256:
            raise StudioError("duplicate or full tile palette")
        return _replace_layer(project, index, replace(layer, palette=layer.palette + (name,)))
    if action == "palette_replace":
        target = _integer(args, "index", 0, len(layer.palette) - 1)
        name = _name(args, "value")
        if name in layer.palette and layer.palette[target] != name:
            raise StudioError("palette names must remain unique")
        p = list(layer.palette)
        p[target] = name
        return _replace_layer(project, index, replace(layer, palette=tuple(p)))
    if action == "palette_swap":
        a = _integer(args, "a", 0, len(layer.palette) - 1)
        b = _integer(args, "b", 0, len(layer.palette) - 1)
        p = list(layer.palette)
        p[a], p[b] = p[b], p[a]
        mapped = tuple(b if cell == a else a if cell == b else cell for cell in data)
        return _replace_layer(project, index, replace(layer, palette=tuple(p), data=mapped))
    if action == "palette_remove":
        target = _integer(args, "index", 0, len(layer.palette) - 1)
        if len(layer.palette) == 1 or target in layer.data:
            raise StudioError("cannot remove last or referenced palette item")
        p = layer.palette[:target] + layer.palette[target + 1:]
        return _replace_layer(project, index, replace(
            layer, palette=p, data=tuple(v - 1 if v > target else v for v in data)))
    if action in ("layer_resize", "layer_crop"):
        width, height = _width_height(args)
        ox = _integer(args, "x", 0, layer.width - 1) if action == "layer_crop" else 0
        oy = _integer(args, "y", 0, layer.height - 1) if action == "layer_crop" else 0
        if action == "layer_crop" and (ox + width > layer.width or oy + height > layer.height):
            raise StudioError("crop must fit existing source")
        fill = _tile(layer, args, "fill") if action == "layer_resize" else -1
        result = [fill] * (width * height)
        for y in range(height):
            for x in range(width):
                sx, sy = x + ox, y + oy
                if sx < layer.width and sy < layer.height:
                    result[y * width + x] = layer.data[sy * layer.width + sx]
        return _replace_layer(project, index, replace(
            layer, width=width, height=height, data=tuple(result)))
    if action == "layer_clear":
        return _replace_layer(project, index, replace(layer, data=(-1,) * len(data)))
    if action == "tile_set":
        x, y = _xy(layer, args)
        data[_inside(layer, x, y)] = _tile(layer, args)
    elif action == "rect_fill":
        x, y, width, height = _rectangle(layer, args)
        tile = _tile(layer, args)
        for row in range(y, y + height):
            data[row * layer.width + x:row * layer.width + x + width] = [tile] * width
    elif action == "line_draw":
        x1, y1 = _xy(layer, args)
        x2 = _integer(args, "x2", 0, layer.width - 1)
        y2 = _integer(args, "y2", 0, layer.height - 1)
        tile = _tile(layer, args)
        dx, dy = abs(x2 - x1), -abs(y2 - y1)
        sx, sy = (1 if x1 < x2 else -1), (1 if y1 < y2 else -1)
        error = dx + dy
        while True:
            data[_inside(layer, x1, y1)] = tile
            if (x1, y1) == (x2, y2):
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x1 += sx
            if twice <= dx:
                error += dx
                y1 += sy
    elif action == "ellipse_fill":
        x, y, width, height = _rectangle(layer, args)
        tile = _tile(layer, args)
        rx, ry = width / 2, height / 2
        for yy in range(y, y + height):
            for xx in range(x, x + width):
                if ((xx + .5 - (x + rx)) / rx) ** 2 + (
                    (yy + .5 - (y + ry)) / ry) ** 2 <= 1:
                    data[_inside(layer, xx, yy)] = tile
    elif action == "flood_fill":
        x, y = _xy(layer, args)
        tile = _tile(layer, args)
        old = data[_inside(layer, x, y)]
        if old != tile:
            queue = deque([(x, y)])
            data[_inside(layer, x, y)] = tile
            while queue:
                px, py = queue.popleft()
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if 0 <= nx < layer.width and 0 <= ny < layer.height:
                        position = _inside(layer, nx, ny)
                        if data[position] == old:
                            data[position] = tile
                            queue.append((nx, ny))
    elif action == "replace_tile":
        before = _tile(layer, args, "before")
        after = _tile(layer, args, "after")
        data = [after if value == before else value for value in data]
    elif action == "checker_fill":
        x, y, width, height = _rectangle(layer, args)
        a, b = _tile(layer, args, "a"), _tile(layer, args, "b")
        for yy in range(y, y + height):
            for xx in range(x, x + width):
                data[_inside(layer, xx, yy)] = a if (xx + yy) % 2 == 0 else b
    elif action in ("stamp", "region_paste"):
        x, y = _xy(layer, args)
        width, height = _width_height(args)
        pixels = args.get("tiles")
        if (type(pixels) is not list or len(pixels) != width * height
                or len(pixels) > 65536 or
                any(type(v) is not int or not -1 <= v < len(layer.palette) for v in pixels)):
            raise StudioError("stamp requires exact bounded source tile buffer")
        if x + width > layer.width or y + height > layer.height:
            raise StudioError("stamp escapes current layer")
        for yy in range(height):
            for xx in range(width):
                value = pixels[yy * width + xx]
                if action == "stamp" and value == -1:
                    continue  # alpha tile in brush stamps
                data[_inside(layer, x + xx, y + yy)] = value
    elif action == "shift_layer":
        dx = _integer(args, "dx", -layer.width, layer.width)
        dy = _integer(args, "dy", -layer.height, layer.height)
        wrap = args.get("wrap", False)
        if type(wrap) is not bool:
            raise StudioError("wrap must be boolean")
        out = [-1] * len(data)
        for y in range(layer.height):
            for x in range(layer.width):
                xx, yy = x + dx, y + dy
                if wrap:
                    xx %= layer.width
                    yy %= layer.height
                if 0 <= xx < layer.width and 0 <= yy < layer.height:
                    out[_inside(layer, xx, yy)] = data[_inside(layer, x, y)]
        data = out
    elif action == "flip_horizontal":
        data = [data[y * layer.width + layer.width - 1 - x]
                for y in range(layer.height) for x in range(layer.width)]
    elif action == "flip_vertical":
        data = [data[(layer.height - 1 - y) * layer.width + x]
                for y in range(layer.height) for x in range(layer.width)]
    elif action == "rotate_90":
        clockwise = args.get("clockwise", True)
        if type(clockwise) is not bool:
            raise StudioError("clockwise must be boolean")
        new_width, new_height = layer.height, layer.width
        new_data = [-1] * len(data)
        for y in range(layer.height):
            for x in range(layer.width):
                nx, ny = ((layer.height - 1 - y, x) if clockwise
                          else (y, layer.width - 1 - x))
                new_data[ny * new_width + nx] = data[_inside(layer, x, y)]
        return _replace_layer(project, index, replace(
            layer, width=new_width, height=new_height, data=tuple(new_data)))
    else:
        raise StudioError("unknown map action")
    return _replace_layer(project, index, replace(layer, data=tuple(data)))
