"""Evidence-bound multidomain studio upscaling using canonical GameForge assets.

Produces REAL original sprite-sheet PNG frames, procedural stage dressing,
parallax/camera decisions and whole-project inventory. It never claims that
numeric previews are native consoles or promoted model weights.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from skeleton.developer.jeeves_game_upscale import _path, _policy
from skeleton.developer.jeeves_game_authoring import _create_only
from skeleton.jeeves.game_console_assets import decode_png, png_rgba

SCHEMA = "skeleton.jeeves.multidomain_upscale.v1"
STAGE_SCHEMA = "skeleton.jeeves.stage_source.v1"
MAX_STAGE_BYTES = 512 * 1024
MAX_STAGE_CELLS = 128 * 128
DOMAINS = ("asset", "animation", "environment", "shadow", "clutter",
           "foliage", "parallax", "stage", "music")
PATTERNS = ("wind", "breathe", "bob", "shimmer", "water")
QA = ("visual_identity", "era_fidelity", "temporal_coherence", "shadow_stability",
      "spatial_readability", "environment_density", "asset_coverage",
      "runtime_performance", "originality", "gameplay_preservation")


class WorldUpscaleError(ValueError):
    pass


def _strict(pairs):
    doc = {}
    for k, v in pairs:
        if k in doc:
            raise WorldUpscaleError("duplicate JSON key")
        doc[k] = v
    return doc


def _source_json(root: Path, path: str) -> tuple[dict[str, Any], str]:
    from skeleton.developer.jeeves_game_quality import _read
    payload, digest = _read(root, path, MAX_STAGE_BYTES)
    return payload, digest


def _write_json(root: Path, name: str, payload: dict[str, Any], *, dry_run=False):
    if not isinstance(name, str) or not name.startswith("design/") or "\\" in name:
        raise WorldUpscaleError("stage output must be inside design/")
    parts = name.split("/")
    if len(parts) != 2 or not parts[1].endswith(".json") or any(
        p in (".", "..", "") for p in parts
    ):
        raise WorldUpscaleError("invalid stage output path")
    target = root / name
    if any(p.is_symlink() for p in (root / "design", target)):
        raise WorldUpscaleError("symlinked design output forbidden")
    if target.exists():
        raise WorldUpscaleError("cannot overwrite stage output")
    encoded = json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True).encode("utf-8") + b"\n"
    if not dry_run:
        _create_only(target, encoded)
    return sha256(encoded).hexdigest()


def _frame_at(data: bytes, width: int, height: int, x: int, y: int) -> bytes:
    if not (0 <= x < width and 0 <= y < height):
        return b"\0\0\0\0"
    i = (y * width + x) * 4
    return data[i:i+4]


def _layer_frame(data: bytes, width: int, height: int, dx: int, dy: int,
                 *, shadow: bool, detail: bool, light: int) -> bytes:
    """Stable compositing, source silhouette retained with grounded shadows."""
    out = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            # Offset shadow only inside authored frame. Never wrap into a neighbor.
            if shadow:
                r, g, b, a = _frame_at(data, width, height, x-dx-1, y-dy-1)
                if a:
                    p = (y*width+x)*4
                    out[p:p+4] = bytes((0, 0, 0, min(105, (a*105)//255)))
    for y in range(height):
        for x in range(width):
            sx, sy = x - dx, y - dy
            r, g, b, a = _frame_at(data, width, height, sx, sy)
            if not a:
                continue
            if detail:
                left = _frame_at(data, width, height, sx-1, sy)
                right = _frame_at(data, width, height, sx+1, sy)
                top = _frame_at(data, width, height, sx, sy-1)
                bottom = _frame_at(data, width, height, sx, sy+1)
                # Contrast-enhance only opaque edges, not transparent contours.
                nearby = (left, right, top, bottom)
                if all(n[3] == 255 for n in nearby) and a == 255:
                    average = [sum(n[channel] for n in nearby)//4 for channel in range(3)]
                    r, g, b = (max(0,min(255,v + (v - avg)//4))
                               for v,avg in zip((r,g,b),average))
            if light:
                r,g,b = (max(0,min(255,v + light)) for v in (r,g,b))
            p = (y * width + x) * 4
            # Original subject takes priority over its cast shadow.
            out[p:p+4] = bytes((r,g,b,a))
    return bytes(out)


def animate(root: Path, *, source: str, output: str, target: str,
            pattern: str = "wind", frames: int = 8,
            frame_height: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Static -> animated; existing vertical strip -> enhanced strip.

    Small bounded deterministic transformations, not a neural animator.
    The last loop frame matches the first position/lighting to avoid seams.
    """
    if pattern not in PATTERNS:
        raise WorldUpscaleError("unsupported authored animation grammar")
    if type(frames) is not int or not 4 <= frames <= 32:
        raise WorldUpscaleError("animation frames per slice must be 4..32")
    if frame_height is not None and (type(frame_height) is not int or frame_height < 1):
        raise WorldUpscaleError("invalid original frame height")
    policy = _policy(target)
    raw = _path(root, source, must_exist=True).read_bytes()
    dest = _path(root, output, must_exist=False)
    w, h, rgba = decode_png(raw)
    fh = frame_height if frame_height is not None else h
    if h % fh or fh < 2 or w < 2:
        raise WorldUpscaleError("animation input must have rectangular vertically stacked frames")
    source_frames = h // fh
    if source_frames > 128 or w*fh*frames > 1024*1024:
        raise WorldUpscaleError("animation output exceeds canonical pixel budget; use chunked clips")
    outputs = []
    for i in range(frames):
        phase = 2 * math.pi * i / (frames-1)
        source_index = (i * source_frames) // frames
        source_index = min(source_frames-1, source_index)
        src = rgba[source_index * w*fh*4:(source_index+1)*w*fh*4]
        dx = round(math.sin(phase)) if pattern in ("wind", "water") else 0
        dy = round(math.sin(phase)) if pattern in ("breathe", "bob", "water") else 0
        light = round(6 * (1-math.cos(phase))) if pattern == "shimmer" else 0
        outputs.append(_layer_frame(src, w, fh, dx, dy,
                                    shadow=True, detail=True, light=light))
    # One loop closure for existing animated sheets does not imply source
    # poses match; the ending pose still gets checked by a reviewer.
    if source_frames == 1:
        outputs[-1] = outputs[0]
    encoded = png_rgba(b"".join(outputs), w, fh*frames)
    result = {
        "ok": True, "action": "upscale-animation", "schema": SCHEMA,
        "target": policy["target_id"], "era": policy["era"],
        "source": source, "output": output, "source_sha256": sha256(raw).hexdigest(),
        "output_sha256": sha256(encoded).hexdigest(), "pattern": pattern,
        "source_frames": source_frames, "output_frames": frames,
        "frame_dimensions": [w, fh], "detail_enhanced": True,
        "contact_shadow_layer": True, "static_animated": source_frames == 1,
        "source_retained": True, "independent_temporal_review": False,
        "native_console_rendering_proven": False, "dry_run": dry_run,
    }
    if not dry_run:
        _create_only(dest, encoded)
        from skeleton.developer.jeeves_game_upscale_queue import record_output
        result["training_candidate"] = record_output(
            root, category="animation", source=source, output=output,
            input_sha256=result["source_sha256"], output_sha256=result["output_sha256"],
            target=policy["target_id"], quality="requires_review",
        )
    return result


def _grid(grid: Any) -> tuple[int, int, list[str]]:
    if not isinstance(grid, list) or not 4 <= len(grid) <= 128:
        raise WorldUpscaleError("stage grid needs 4..128 authored rows")
    if any(not isinstance(row, str) for row in grid):
        raise WorldUpscaleError("stage map rows must be text")
    width = len(grid[0])
    if not 4 <= width <= 128 or any(len(row) != width for row in grid):
        raise WorldUpscaleError("stage grid must be rectangular with 4..128 columns")
    if any(char not in ".#SG" for row in grid for char in row):
        raise WorldUpscaleError("stage grid may contain only walkable, wall, start and goal")
    if sum(row.count("S") for row in grid) != 1 or sum(row.count("G") for row in grid) != 1:
        raise WorldUpscaleError("stage requires one start and one goal")
    return width, len(grid), grid


def _route(grid: list[str]) -> list[list[int]]:
    w, h = len(grid[0]), len(grid)
    sy = next(i for i,row in enumerate(grid) if "S" in row)
    start = (grid[sy].index("S"), sy)
    visited = {start: None}
    queue = deque([start])
    end = None
    while queue:
        x,y = queue.popleft()
        if grid[y][x] == "G":
            end = (x,y)
            break
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] != "#" and (nx,ny) not in visited:
                visited[(nx,ny)] = (x,y)
                queue.append((nx,ny))
    if end is None:
        raise WorldUpscaleError("stage has no traversable path; upscale cannot mask broken game")
    steps = []
    while end is not None:
        steps.append([*end])
        end = visited[end]
    return steps[::-1]


def camera_profile(depth: str, *, yaw: float = 0, pitch: float = 0,
                   parallax_planes: int = 3) -> dict[str, Any]:
    if depth not in ("2d", "2_5d", "2_9d", "3d"):
        raise WorldUpscaleError("unsupported camera dimensional grammar")
    for name,val in (("yaw",yaw),("pitch",pitch)):
        if type(val) not in (int,float) or not math.isfinite(val):
            raise WorldUpscaleError("invalid camera angle")
    if type(parallax_planes) is not int or not 1 <= parallax_planes <= 32:
        raise WorldUpscaleError("parallax requires 1..32 independently authored planes")
    limits = {"2d": (0,0), "2_5d": (45,20), "2_9d": (90,45), "3d": (180,89)}
    max_yaw,max_pitch = limits[depth]
    if abs(yaw) > max_yaw or abs(pitch) > max_pitch:
        raise WorldUpscaleError("camera rotation exceeds declared scene depth support")
    yy,pp = math.radians(yaw),math.radians(pitch)
    cy,sy = math.cos(yy), math.sin(yy)
    cp,sp = math.cos(pp), math.sin(pp)
    rotation = [
        [cy, sy*sp, sy*cp],
        [0.0, cp, -sp],
        [-sy, cy*sp, cy*cp],
    ]
    return {
        "ok": True, "action": "camera-plan", "depth": depth,
        "yaw_deg": yaw, "pitch_deg": pitch, "rotation_matrix": rotation,
        "camera_rotation_supported": depth != "2d",
        "parallax_planes": parallax_planes,
        "parallax_depth_weights": [round(1/(1+i),6) for i in range(parallax_planes)],
        "billboard_orientation_review_required": depth != "2d",
        "occlusion_test_required": depth != "2d",
        "collision_projection_preserved": True,
        "actual_scene_rotated": False,
    }


def stage(root: Path, *, source: str, output: str, target: str,
          richness: int = 3, dry_run: bool = False) -> dict[str, Any]:
    """Real decorated stage JSON, authored collision map and route unchanged."""
    policy = _policy(target)
    if type(richness) is not int or not 1 <= richness <= 5:
        raise WorldUpscaleError("richness requires ordinal 1..5")
    spec, src_sha = _source_json(root, source)
    if set(spec) != {"schema", "grid", "depth", "biome", "layers", "camera"} or spec["schema"] != STAGE_SCHEMA:
        raise WorldUpscaleError("invalid authored stage schema")
    w,h,grid = _grid(spec["grid"])
    if not isinstance(spec["biome"],str) or spec["biome"] not in (
        "forest","desert","city","mountain","underwater","industrial","space"
    ):
        raise WorldUpscaleError("unsupported original stage biome")
    cam = spec["camera"]
    if not isinstance(cam,dict) or set(cam) != {"yaw","pitch"}:
        raise WorldUpscaleError("invalid stage camera")
    layers = spec["layers"]
    if not isinstance(layers,list) or not 1 <= len(layers) <= 24:
        raise WorldUpscaleError("stage requires 1..24 authored parallax layers")
    bound_layers=[]
    for item in layers:
        if not isinstance(item,dict) or set(item) != {"path","depth"}:
            raise WorldUpscaleError("every stage plane must have asset path and depth")
        asset = _path(root,item["path"],must_exist=True)
        depth = item["depth"]
        if type(depth) not in (float,int) or not math.isfinite(depth) or not 0 <= depth <= 1:
            raise WorldUpscaleError("invalid stage parallax depth")
        bound_layers.append({"asset_path":item["path"],
                             "asset_sha256":sha256(asset.read_bytes()).hexdigest(),
                             "depth":depth, "parallax_factor":round(1/(1+depth*3),6)})
    path = _route(grid)
    occupied = {tuple(x) for x in path}
    # World dressing is non-colliding, within walkable cells and away from
    # original start/end. Critical navigation remains byte-for-byte intact.
    palette = {
        "forest":("foliage","clutter","ambient_particles"),
        "desert":("clutter","dust","shadow"),
        "city":("clutter","lighting","shadow"),
        "mountain":("foliage","fog","shadow"),
        "underwater":("foliage","caustic_light","particles"),
        "industrial":("clutter","steam","shadow"),
        "space":("clutter","ambient_particles","lighting"),
    }[spec["biome"]]
    positions = []
    seed = int(sha256((src_sha+str(richness)).encode()).hexdigest()[:12],16)
    for y,row in enumerate(grid):
        for x,char in enumerate(row):
            if char != "." or (x,y) in occupied:
                continue
            val = int(sha256(f"{seed}:{x}:{y}".encode()).hexdigest()[:8],16)
            if val % 10 < richness:
                kind = palette[val % len(palette)]
                positions.append({"x":x, "y":y, "kind":kind,
                                  "collidable":False,"source":"procedural_original_stage_detail"})
    camera = camera_profile(spec["depth"], yaw=cam["yaw"], pitch=cam["pitch"],
                            parallax_planes=len(layers))
    out = {
        **spec, "enhancement": {
            "schema": SCHEMA, "source_sha256":src_sha, "target":policy["target_id"],
            "richness":richness, "dressing":positions,
            "parallax":bound_layers, "camera":camera,
            "route_verified":True, "start_to_goal_route":path,
            "collision_map_unchanged":True,
            "assets_rechecked":len(bound_layers),
            "independent_vividness_review":False,
        }
    }
    digest = _write_json(root,output,out,dry_run=dry_run)
    result = {
        "ok":True, "action":"upscale-stage", "source":source, "output":output,
        "source_sha256":src_sha, "output_sha256":digest,
        "dressing_count":len(positions), "assets_considered":len(bound_layers),
        "navigable_route_steps":len(path), "collision_map_unchanged":True,
        "camera":camera, "biome":spec["biome"], "dry_run":dry_run,
        "gameplay_test_performed":False, "production_qualified":False,
    }
    if not dry_run:
        from skeleton.developer.jeeves_game_upscale_queue import record_output
        result["training_candidate"] = record_output(
            root,category="stage",source=source,output=output,
            input_sha256=src_sha,output_sha256=digest,target=policy["target_id"],
            quality="requires_review")
    return result


def inventory(root:Path, *, page:int=0, page_size:int=128) -> dict[str,Any]:
    """Inventory ALL discoverable project assets with deterministic pagination.

    No lifetime max assets, only a bounded response page. Symlinks and unknown
    media stay visible as deficiencies; none is silently omitted as 'good'.
    """
    from skeleton.developer.game_cli import _load
    _load(root)
    if type(page) is not int or page < 0 or type(page_size) is not int or not 1 <= page_size <= 512:
        raise WorldUpscaleError("inventory pagination invalid")
    folders = ("assets","design")
    relevant = (".png",".gif",".wav",".mp3",".ogg",".flac",".json",".md",
                ".mp4",".webm",".obj",".glb",".gltf",".tscn",".gdshader",
                ".shader",".ttf",".otf",".svg")
    results = []
    counters = {d:0 for d in DOMAINS}
    total = 0
    first = page * page_size
    for folder_name in folders:
        folder = root / folder_name
        if folder.is_symlink():
            raise WorldUpscaleError("asset inventory root may not be symlinked")
        if not folder.exists():
            continue
        for f in sorted(folder.rglob("*")):
            if f.is_dir():
                if f.is_symlink():
                    raise WorldUpscaleError("symlinked inventory directory")
                continue
            if f.is_symlink() or not f.is_file():
                raise WorldUpscaleError("nonregular or symlinked asset source in project")
            relative = f.relative_to(root).as_posix()
            name = f.name.lower()
            kind = ("music" if f.suffix.lower() in (".wav",".mp3",".ogg",".flac")
                    else "animation" if "anim" in name or "sprite_sheet" in name
                    else "foliage" if any(n in name for n in ("tree","bush","grass","leaf"))
                    else "shadow" if "shadow" in name
                    else "parallax" if "parallax" in name or "background" in name
                    else "stage" if f.suffix.lower() == ".tscn" or "stage" in name
                    else "environment" if "environment" in name or "weather" in name
                    else "clutter" if "clutter" in name or "prop" in name
                    else "asset")
            counters[kind] += 1
            if first <= total < first + page_size:
                # A byte digest is real provenance, without loading media into model context.
                h = sha256()
                with f.open("rb") as inp:
                    for part in iter(lambda:inp.read(1<<20), b""):
                        h.update(part)
                results.append({"path":relative, "domain":kind,"bytes":f.stat().st_size,
                                "sha256":h.hexdigest(),
                                "recognized_format":f.suffix.lower() in relevant,
                                "independent_asset_qa":False})
            total += 1
    return {
        "ok":True,"action":"asset-inventory","schema":SCHEMA,
        "total_assets_and_design_files":total,"domain_counts":counters,
        "page":page,"page_size":page_size,"entries":results,
        "next_page":page+1 if total>(page+1)*page_size else None,
        "full_project_independently_reviewed":False,
        "all_discoverable_paths_accounted_for":True,
    }


def scrutiny(root:Path, *, passes:int=3) -> dict[str,Any]:
    """Multi-parse full inventory; do not call visual aesthetics 'verified'."""
    if type(passes) is not int or not 1 <= passes <= 8:
        raise WorldUpscaleError("1..8 scrutiny passes per resumable invocation")
    audits=[]
    for i in range(passes):
        start=0
        digest=sha256()
        count=0
        while True:
            page=inventory(root,page=start,page_size=256)
            for row in page["entries"]:
                digest.update(json.dumps([row["path"],row["sha256"],row["bytes"]],
                                         separators=(",",":"),sort_keys=True).encode())
            count+=len(page["entries"])
            if page["next_page"] is None:
                break
            start=page["next_page"]
        audits.append({"pass":i+1,"files_rechecked":count,
                       "project_asset_digest":digest.hexdigest(),
                       "real_file_hash_evidence":True})
    consistent=len({r["project_asset_digest"] for r in audits})==1
    return {
        "ok":consistent,"action":"upscale-review","scrutiny_passes":passes,
        "complete_asset_inventory_reparsed":True,
        "passes":audits,"source_stable_during_scrutiny":consistent,
        "domains_required":list(DOMAINS),"quality_dimensions":list(QA),
        "independent_era_quality_review":False,
        "all_assets_expert_reviewed":False,
        "gameplay_playthrough_verified":False,
        "production_qualified":False,
    }
