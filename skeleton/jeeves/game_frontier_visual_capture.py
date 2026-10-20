"""Godot viewport-frame capture ingestion with explicit untrusted provenance.

The engine-side script emits original RGB data and game/geometry metadata.
The Python verifier validates format, frame ordering, and pixel SHA-256 before
Dragon's visual lab is allowed to compare the data. Native origin is a claim
until backed by an authenticated runner, not by output strings alone.
"""
from __future__ import annotations
from base64 import b64decode
from binascii import Error as Base64Error
from hashlib import sha256
from typing import Mapping
import json
from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_visual_lab import VisualFrame,compare_original_visuals
PREFIX="EXPEDITION_VIEWPORT_RGB "
MAX_FRAMES=120

def ingest_godot_viewport_log(log:str,*,expected_world:str,
                              expected_kind:str="original_runtime_capture")->dict:
    if (type(log) is not str or len(log)>2_000_000 or type(expected_world) is not str
            or len(expected_world)!=64):
        raise ExpeditionError("native gameplay frame log length/source invalid")
    frames=[]
    for line in log.splitlines():
        if not line.startswith(PREFIX):
            continue
        if len(frames)>=MAX_FRAMES or len(line)>65536:
            raise ExpeditionError("native frame capture exceeds output budget")
        try:
            row=json.loads(line[len(PREFIX):])
        except ValueError as exc:
            raise ExpeditionError("native viewport frame evidence invalid JSON") from exc
        if (type(row) is not dict or
                set(row)!={"world_digest","frame","width","height",
                           "pixel_sha256","rgb_base64","kind"} or
                row["world_digest"]!=expected_world or row["kind"]!=expected_kind):
            raise ExpeditionError("native viewport source claims are malformed or foreign")
        try:
            raw=b64decode(row["rgb_base64"],validate=True)
        except (TypeError,ValueError,Base64Error) as exc:
            raise ExpeditionError("native viewport RGB data corrupt") from exc
        actual=VisualFrame(expected_world,row["frame"],row["width"],
                           row["height"],raw,row["kind"])
        if actual.source_digest=="0"*64 or sha256(raw).hexdigest()!=row["pixel_sha256"]:
            raise ExpeditionError("native viewport image checksum mismatched")
        if frames and frames[-1].frame>=actual.frame:
            raise ExpeditionError("native viewport capture frame order not monotonic")
        frames.append(actual)
    if len(frames)<2:
        raise ExpeditionError("native viewport needs two real comparable frames")
    scored=compare_original_visuals((tuple(frames),))
    report={"schema":"skeleton.dragon.native_viewport_ingest.v1",
            "world":expected_world,"frames":len(frames),
            "pixel_sources":[x.source_digest for x in frames],
            "comparison":scored["receipt_digest"],
            "native_runner_attestation_verified":False,
            "video_file_generated":False}
    report["receipt_digest"]=_digest(report)
    return {"frames":tuple(frames),"report":report,"comparison":scored}

_GODOT_CAPTURE="""extends SceneTree
# Emits two bounded original viewport RGB frames, no fabricated pixel metadata.
const WIDTH = 24
const HEIGHT = 16
const WORLD_FILE = "res://game/frontier/expedition.json"

func _initialize() -> void:
    call_deferred("_capture_original")

func _hash_packed_bytes(data: PackedByteArray) -> String:
    var digest := HashingContext.new()
    digest.start(HashingContext.HASH_SHA256)
    digest.update(data)
    return digest.finish().hex_encode()

func _capture_original() -> void:
    var world_path := "res://game/frontier/expedition.json"
    if not FileAccess.file_exists(world_path):
        push_error("Missing original game world for pixel capture")
        quit(71)
        return
    var data = JSON.parse_string(FileAccess.get_file_as_string(world_path))
    if typeof(data) != TYPE_DICTIONARY:
        quit(72)
        return
    var digest: String = str(data.get("world_digest", ""))
    if digest.length() != 64:
        quit(73)
        return
    var scene := Node3D.new()
    root.add_child(scene)
    for i in range(2):
        var box := MeshInstance3D.new()
        box.mesh = BoxMesh.new()
        box.position = Vector3(float(i)*3.0,0,0)
        scene.add_child(box)
    var camera := Camera3D.new()
    camera.position = Vector3(0,3,8)
    scene.add_child(camera)
    camera.look_at(Vector3.ZERO,Vector3.UP)
    camera.current = true
    for n in range(2):
        camera.position.x = float(n)*2.0
        await process_frame
        await process_frame
        var picture: Image = root.get_viewport().get_texture().get_image()
        if picture == null or picture.is_empty():
            push_error("Native viewport capture returned no real image")
            quit(74)
            return
        picture.resize(WIDTH,HEIGHT)
        picture.convert(Image.FORMAT_RGB8)
        var pixels: PackedByteArray = picture.get_data()
        if pixels.size() != WIDTH*HEIGHT*3:
            quit(75)
            return
        print("EXPEDITION_VIEWPORT_RGB " + JSON.stringify({
            "world_digest":digest,"frame":n,
            "width":WIDTH,"height":HEIGHT,
            "kind":"original_runtime_capture",
            "pixel_sha256":_hash_packed_bytes(pixels),
            "rgb_base64":Marshalls.raw_to_base64(pixels),
        }))
    quit(0)
"""

def export_native_capture_godot()->dict[str,str]:
    return {"game/frontier/viewport_capture.gd":_GODOT_CAPTURE}
