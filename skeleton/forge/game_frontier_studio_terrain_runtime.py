"""Compile authored Studio terrain tiles into actual visible Godot 4 MultiMesh geometry.

This is native game content, not a source receipt alone: each nonblank tile is
placed into a 3D renderer with palette-derived material colour and authored
elevation. MultiMesh batches draw calls; max 8192 instances across all layers
keeps low-memory targets bounded. Existing expedition script/gameplay is kept.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Mapping

from .game_frontier_studio import StudioProject, StudioError, compile_studio_project

_SCENE = "game/frontier/expedition.tscn"
_SCRIPT = "game/frontier/studio_terrain.gd"
_DATA = "game/frontier/studio_terrain.json"
_LIMIT = 8192

_TERRAIN_GDSCRIPT = r'''extends Node3D
# Real visible source-authored terrain, batched for low-memory Godot 4 targets.
const TERRAIN_PATH := "res://game/frontier/studio_terrain.json"
const MAX_CELLS := 8192

func _ready() -> void:
    if not FileAccess.file_exists(TERRAIN_PATH):
        push_error("Studio terrain source missing")
        return
    var text: String = FileAccess.get_file_as_string(TERRAIN_PATH)
    if text.length() > 2000000:
        push_error("Studio terrain source exceeded budget")
        return
    var data: Variant = JSON.parse_string(text)
    if typeof(data) != TYPE_DICTIONARY:
        push_error("Studio terrain must be an object")
        return
    if str(data.get("schema", "")) != "skeleton.forge.godot_studio_terrain.v1":
        push_error("Studio terrain source schema mismatch")
        return
    var layers: Array = data.get("layers", [])
    if layers.size() > 128:
        push_error("Too many terrain layers")
        return
    var total: int = 0
    for layer in layers:
        if typeof(layer) != TYPE_DICTIONARY:
            return
        var width: int = int(layer.get("width", 0))
        var height: int = int(layer.get("height", 0))
        var tiles: Array = layer.get("tiles", [])
        var palette: Array = layer.get("palette", [])
        if width < 1 or height < 1 or width > 256 or height > 256:
            return
        if tiles.size() != width * height or palette.is_empty() or palette.size() > 256:
            return
        var count: int = 0
        for tile in tiles:
            if int(tile) >= 0:
                count += 1
        if count > MAX_CELLS - total:
            push_error("Studio terrain runtime instance budget exceeded")
            return
        if count == 0:
            continue
        var block := BoxMesh.new()
        block.size = Vector3(0.96, 0.18, 0.96)
        var surface := StandardMaterial3D.new()
        surface.vertex_color_use_as_albedo = true
        surface.roughness = 0.94
        block.material = surface
        var mesh := MultiMesh.new()
        mesh.transform_format = MultiMesh.TRANSFORM_3D
        mesh.use_colors = true
        mesh.mesh = block
        mesh.instance_count = count
        var altitude: float = float(layer.get("elevation_m", 0.0))
        var instance: int = 0
        for y in range(height):
            for x in range(width):
                var tile: int = int(tiles[y * width + x])
                if tile < 0 or tile >= palette.size():
                    continue
                var position := Vector3(float(x), altitude, float(y))
                mesh.set_instance_transform(instance, Transform3D(Basis.IDENTITY, position))
                var hue: float = float(posmod(str(palette[tile]).hash(), 360)) / 360.0
                mesh.set_instance_color(instance, Color.from_hsv(hue, 0.44, 0.78))
                instance += 1
        var rendered := MultiMeshInstance3D.new()
        rendered.multimesh = mesh
        rendered.name = "Terrain_" + str(layer.get("id", "layer"))
        add_child(rendered)
        total += count
    print("STUDIO_TERRAIN_READY " + str(data.get("studio_sha256", "")) + " " + str(total))
'''


def add_studio_native_terrain(project: StudioProject,
                              files: Mapping[str, str]) -> dict[str, str]:
    """Append visible source tiles to original Godot project with exact lineage."""
    if not isinstance(project, StudioProject) or not isinstance(files, Mapping):
        raise StudioError("source project and native export files required")
    original=dict(files)
    if any(x in original for x in (_SCRIPT,_DATA)):
        raise StudioError("native terrain export would replace existing authored files")
    if _SCENE not in original:
        raise StudioError("native terrain must attach to existing expedition root")
    layers=[]
    drawn=0
    for layer in project.layers:
        count=sum(value>=0 for value in layer.data)
        if count == 0:
            continue
        remaining=_LIMIT-drawn
        if count>remaining:
            # Explicit deterministic coarse LOD for large authored layers.
            stride=max(2,math.ceil(math.sqrt(count/max(1,remaining))))
            sampled=[]
            for y in range(0,layer.height,stride):
                for x in range(0,layer.width,stride):
                    index=y*layer.width+x
                    if layer.data[index]>=0:
                        sampled.append((x,y,layer.data[index]))
            if len(sampled)>remaining:
                sampled=sampled[:remaining]
            # Keep full original coordinates by using an erased sparse grid.
            values=[-1]*len(layer.data)
            for x,y,value in sampled:
                values[y*layer.width+x]=value
        else:
            values=list(layer.data)
        count=sum(value>=0 for value in values)
        if count>remaining:
            raise StudioError("native terrain exceeds renderer instance budget")
        drawn+=count
        layers.append({
            "id":layer.layer_id,"width":layer.width,"height":layer.height,
            "elevation_m":layer.elevation_m,
            "palette":list(layer.palette),"tiles":values,
            "source_nonempty_cells":sum(v>=0 for v in layer.data),
            "rendered_cells":count,
        })
        if drawn >= _LIMIT:
            break
    result={
        "schema":"skeleton.forge.godot_studio_terrain.v1",
        "studio_sha256":compile_studio_project(project)["content_sha256"],
        "source_layer_count":len(project.layers),
        "rendered_layer_count":len(layers),
        "rendered_cells":drawn,
        "source_cells":sum(sum(v>=0 for v in layer.data) for layer in project.layers),
        "visual_lod_only":True,"collision_unmodified":True,
        "layers":layers,
    }
    if result["rendered_cells"]==0:
        return original
    record=json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False)
    if len(record.encode())>2_000_000:
        raise StudioError("native terrain record exceeds byte budget")
    scene=original[_SCENE]
    marker=re.search(r"\[gd_scene load_steps=(\d+) format=3\]",scene)
    if marker is None:
        raise StudioError("Godot expedition scene must expose typed resource header")
    step=int(marker.group(1))
    if not 2<=step<=10:
        raise StudioError("original scene has unexpected resource count")
    extension_id=str(step)
    ext=f'[ext_resource type="Script" path="res://{_SCRIPT}" id="{extension_id}"]'
    if ext in scene:
        raise StudioError("terrain scene script already exists")
    scene=scene.replace(marker.group(0),f"[gd_scene load_steps={step+1} format=3]",1)
    previous='[ext_resource type="Script" path="res://game/frontier/expedition.gd" id="1"]'
    if previous not in scene:
        raise StudioError("native terrain root does not have original engine script")
    scene=scene.replace(previous,previous+"\n"+ext,1)
    scene+=f'\n[node name="StudioTerrain" type="Node3D" parent="."]\nscript = ExtResource("{extension_id}")\n'
    original[_SCENE]=scene
    original[_SCRIPT]=_TERRAIN_GDSCRIPT
    original[_DATA]=record
    return original
