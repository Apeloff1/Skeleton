"""All-core runtime RGB observation for authorized game asset design analysis.

Observes actual emulator-owned RGB24 pixels without issuing a single native
retro_run. This is needed when assets are unpacked/decompressed into PPU/GPU
memory and static code/ROM disassembly cannot identify authored graphics.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

MAX_FRAMES = 16
MAX_RGB_BYTES = 4 * 1024 * 1024
GRID = 16


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(obj: Any) -> str:
    return _sha(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode())


def _valid_sha(value: object) -> bool:
    return type(value) is str and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def _validate_frame(frame: Mapping[str, Any], pixels: bytes) -> dict[str, Any]:
    if (not isinstance(frame,dict) or set(frame)!={
        "width","height","pixel_sha256","native_run_cursor",
    } or type(pixels) is not bytes):
        raise ValueError("Exact native RGB24 frame metadata and bytes required")
    width,height=frame["width"],frame["height"]
    if (type(width) is not int or type(height) is not int
        or not 1<=width<=4096 or not 1<=height<=4096
        or width*height*3>MAX_RGB_BYTES
        or len(pixels)!=width*height*3
        or not _valid_sha(frame["pixel_sha256"])
        or _sha(pixels)!=frame["pixel_sha256"]
        or type(frame["native_run_cursor"]) is not int
        or frame["native_run_cursor"]<0):
        raise ValueError("Native RGB extent, checksum or run cursor differs")
    return dict(frame)


def _sampled_visual_features(pixels: bytes, width: int, height: int) -> dict[str, Any]:
    xcount,ycount=min(width,GRID),min(height,GRID)
    tiles = []
    all_r = Counter()
    for by in range(ycount):
        y0,y1=by*height//ycount,(by+1)*height//ycount
        for bx in range(xcount):
            x0,x1=bx*width//xcount,(bx+1)*width//xcount
            # Region SHA covers ALL bytes. Palette histogram samples 16x16
            # even positions, not the entire tile; no misleading label.
            digest=hashlib.sha256()
            for y in range(y0,y1):
                index=(y*width+x0)*3
                digest.update(pixels[index:index+(x1-x0)*3])
            palette=Counter()
            lum=[]
            for yi in range(16):
                y=y0+(yi*(y1-y0-1))//15
                for xi in range(16):
                    x=x0+(xi*(x1-x0-1))//15
                    pos=(y*width+x)*3
                    color=tuple(pixels[pos:pos+3])
                    reduced=tuple(channel//32 for channel in color)
                    palette[reduced]+=1
                    all_r[reduced]+=1
                    lum.append((54*color[0]+183*color[1]+19*color[2])//256)
            tiles.append({
                "x":x0,"y":y0,"width":x1-x0,"height":y1-y0,
                "region_rgb_sha256":digest.hexdigest(),
                "sampled_5bit_palette_bins":len(palette),
                "sampled_luminance_mean":round(sum(lum)/len(lum),3),
                "sampled_luminance_range":[min(lum),max(lum)],
            })
    totals=sum(all_r.values())
    entropy=-sum((n/totals)*math.log2(n/totals) for n in all_r.values()) if totals else 0
    return {
        "tile_columns":xcount,"tile_rows":ycount,
        "regions":tiles,
        "sampled_global_5bit_color_bins":len(all_r),
        "sampled_color_entropy_bits":round(entropy,5),
        "palette_measurement_method":"stratified_16x16_per_tile_5bit_bins",
        "tile_sha256_are_exact_full_region_rgb":True,
        "detected_character_sprite_animation":False,
    }


def observe_native_frames(
    frames: Sequence[tuple[Mapping[str,Any],bytes]], *,
    game_content_sha256: str, core_binary_sha256: str,
    rights_evidence_digest: str, authorize: Callable[[], bool],
) -> dict[str, Any]:
    if not callable(authorize) or authorize() is not True:
        raise PermissionError("Live RGB source and asset-analysis rights not currently authorized")
    if (not isinstance(frames,(tuple,list)) or not 1<=len(frames)<=MAX_FRAMES
        or not all(_valid_sha(x) for x in (
            game_content_sha256,core_binary_sha256,rights_evidence_digest
        ))):
        raise ValueError("Approved source/core lineage and 1–16 bounded frames required")
    dimensions=None
    last_cursor=None
    last_pixels=None
    reports=[]
    change_ratios=[]
    for pair in frames:
        if not isinstance(pair,tuple) or len(pair)!=2:
            raise ValueError("Native frame must be (metadata, verified RGB bytes)")
        raw,pixels=pair
        frame=_validate_frame(raw,pixels)
        size=(frame["width"],frame["height"])
        if dimensions is None:dimensions=size
        if dimensions!=size:
            raise ValueError("Runtime frame geometry changed; split into separate evidence segments")
        if last_cursor is not None and frame["native_run_cursor"]<last_cursor:
            raise ValueError("Native run cursor moved backward without recorded reset")
        if last_cursor is not None and frame["native_run_cursor"]==last_cursor:
            if last_pixels!=pixels:
                raise ValueError("Frame changed without a native emulation run")
        changed=None
        if last_pixels is not None:
            changed=round(sum(a!=b for a,b in zip(last_pixels,pixels,strict=True))/len(pixels),6)
            change_ratios.append(changed)
        feature=_sampled_visual_features(pixels,*size)
        reports.append({
            "frame_index":len(reports),
            "frame_sha256":frame["pixel_sha256"],
            "native_run_cursor":frame["native_run_cursor"],
            "delta_native_runs": (
                None if last_cursor is None else frame["native_run_cursor"]-last_cursor
            ),
            "changed_rgb_byte_ratio_vs_previous":changed,
            "visual_features":feature,
        })
        last_cursor,last_pixels=frame["native_run_cursor"],pixels
    body={
        "schema_version":"skeleton.game.native_rgb_asset_sequence.v1",
        "game_content_sha256":game_content_sha256,
        "core_binary_sha256":core_binary_sha256,
        "rights_evidence_digest":rights_evidence_digest,
        "width":dimensions[0],"height":dimensions[1],
        "frames_measured":len(reports),
        "frame_reports":reports,
        "mean_temporal_rgb_change":(
            round(sum(change_ratios)/len(change_ratios),6) if change_ratios else None
        ),
        "native_frames_executed_by_this_analyzer":0,
        "input_pixel_buffers_returned":False,
        "asset_copy_or_rom_source_exported":False,
        "compressed_runtime_graphics_semantically_recovered":False,
        "gameplay_visual_quality_proven":False,
        "production_model_weights_updated":False,
    }
    body["receipt_sha256"]=_digest(body)
    if len(json.dumps(body,allow_nan=False).encode())>3*1024*1024:
        raise ValueError("Native frame-region evidence exceeds bounded three-MiB receipt")
    return body
