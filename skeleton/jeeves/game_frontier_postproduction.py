"""Source-verified original game post-production: seven executable visual milestones.

Pixels may be untrusted user-provided captures or procedural authoring previews.
Neither pixel-origin labels nor their checksums authenticate the rendering host.
Every output can be rebuilt byte-for-byte and cannot approve publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isqrt
from typing import Mapping

from .game_frontier_expedition import ExpeditionError, _digest
from .game_frontier_expedition_visual_lab import VisualFrame


@dataclass(frozen=True, slots=True)
class PostProductionPolicy:
    max_frames: int = 120
    max_selected: int = 8
    min_frame_spacing: int = 1
    scene_cut_fraction: float = .28
    freeze_fraction: float = .001
    max_sheet_pixels: int = 65536

    def __post_init__(self) -> None:
        if (type(self.max_frames) is not int or not 2 <= self.max_frames <= 120
                or type(self.max_selected) is not int
                or not 2 <= self.max_selected <= min(self.max_frames, 32)
                or type(self.min_frame_spacing) is not int
                or not 1 <= self.min_frame_spacing <= 4096
                or type(self.max_sheet_pixels) is not int
                or not 1024 <= self.max_sheet_pixels <= 262144):
            raise ExpeditionError("post-production resource limits invalid")
        for n in (self.scene_cut_fraction, self.freeze_fraction):
            if type(n) not in (float, int) or not 0 <= n <= 1:
                raise ExpeditionError("post-production visual threshold invalid")
        if self.freeze_fraction >= self.scene_cut_fraction:
            raise ExpeditionError("post-production freeze threshold exceeds scene cut")


def _validate(
    frames: tuple[VisualFrame, ...], expected_world: str,
    policy: PostProductionPolicy,
) -> str:
    if (not isinstance(policy, PostProductionPolicy) or type(frames) is not tuple
            or not 2 <= len(frames) <= policy.max_frames
            or type(expected_world) is not str or len(expected_world) != 64
            or any(c not in "0123456789abcdef" for c in expected_world)):
        raise ExpeditionError("post-production frame scope invalid")
    if any(not isinstance(f, VisualFrame) for f in frames):
        raise ExpeditionError("post-production requires actual bounded RGB source frames")
    first = frames[0]
    if any(f.game_digest != expected_world
           or f.width != first.width or f.height != first.height
           or f.kind != first.kind for f in frames):
        raise ExpeditionError("post-production mixed world, geometry or origin")
    if any(b.frame <= a.frame for a, b in zip(frames, frames[1:])):
        raise ExpeditionError("post-production reordered or duplicate input frame")
    if len({f.source_digest for f in frames}) != len(frames):
        raise ExpeditionError("post-production duplicate source receipts")
    return first.kind


def _luminance(f: VisualFrame) -> tuple[int, ...]:
    raw = f.rgb
    return tuple(
        (54 * raw[i] + 183 * raw[i + 1] + 19 * raw[i + 2]) // 256
        for i in range(0, len(raw), 3)
    )


def _spatial(f: VisualFrame) -> dict:
    """Quantify exposure, contrast, detail and the full 16-bin histogram."""
    lum = _luminance(f)
    count = len(lum)
    hist = [0] * 16
    gradients = []
    for i, v in enumerate(lum):
        hist[min(v // 16, 15)] += 1
        if i % f.width:
            gradients.append(abs(v - lum[i - 1]))
        if i >= f.width:
            gradients.append(abs(v - lum[i - f.width]))
    focus = sum(gradients) / max(1, len(gradients))
    return {
        "frame": f.frame,
        "source_digest": f.source_digest,
        "pixel_sha256": sha256(f.rgb).hexdigest(),
        "exposure_mean": round(sum(lum) / count, 6),
        "shadow_fraction": round(sum(hist[:2]) / count, 6),
        "highlight_fraction": round(sum(hist[14:]) / count, 6),
        "contrast_span": max(lum) - min(lum),
        "gradient_strength": round(focus, 6),
        "edge_fraction": round(
            sum(x >= 24 for x in gradients) / max(1, len(gradients)), 6
        ),
        "histogram_16": hist,
    }


def _temporal(a: VisualFrame, b: VisualFrame, policy: PostProductionPolicy) -> dict:
    delta = sum(abs(x - y) for x, y in zip(a.rgb, b.rgb))
    fraction = round(delta / (255 * len(a.rgb)), 9)
    gap = b.frame - a.frame
    return {
        "from_frame": a.frame, "to_frame": b.frame,
        "frame_gap": gap, "normalized_pixel_change": fraction,
        "frozen": fraction <= policy.freeze_fraction,
        "scene_cut_candidate": fraction >= policy.scene_cut_fraction,
        "unobserved_intermediate_frames": gap - 1,
    }


def _select_frames(stats: list[dict], transitions: list[dict],
                   policy: PostProductionPolicy) -> tuple[int, ...]:
    """Endpoints, scene cuts, then high-information frames; source order retained."""
    by_frame = {s["frame"]: s for s in stats}
    essential = {stats[0]["frame"], stats[-1]["frame"]}
    candidates = [t for t in transitions if t["scene_cut_candidate"]]
    candidates.sort(key=lambda t: (-t["normalized_pixel_change"], t["to_frame"]))
    ranked = [t["to_frame"] for t in candidates]
    ranked += [
        x["frame"] for x in sorted(
            stats[1:-1],
            key=lambda x: (-x["gradient_strength"], -x["contrast_span"], x["frame"]),
        )
    ]
    for index in ranked:
        if len(essential) >= policy.max_selected:
            break
        if index not in by_frame or index in essential:
            continue
        if all(abs(index - old) >= policy.min_frame_spacing for old in essential):
            essential.add(index)
    return tuple(sorted(essential))


def _sheet(frames: tuple[VisualFrame, ...], indices: tuple[int, ...],
           policy: PostProductionPolicy) -> tuple[str, dict]:
    source = {f.frame: f for f in frames}
    selected = [source[i] for i in indices]
    n = len(selected)
    columns = isqrt(n)
    if columns * columns < n:
        columns += 1
    rows = (n + columns - 1) // columns
    width, height = selected[0].width, selected[0].height
    canvas_width, canvas_height = width * columns, height * rows
    if canvas_width * canvas_height > policy.max_sheet_pixels:
        raise ExpeditionError("post-production contact sheet exceeds pixel budget")
    # Plain-text PPM is a genuine portable image and fits UTF-8 game archives.
    black = "0 0 0"
    lines = ["P3", f"{canvas_width} {canvas_height}", "255"]
    for y in range(canvas_height):
        tile_row, local_y = divmod(y, height)
        pixels = []
        for x in range(canvas_width):
            tile_col, local_x = divmod(x, width)
            tile = tile_row * columns + tile_col
            if tile >= n:
                pixels.append(black)
            else:
                rgb = selected[tile].rgb
                pos = (local_y * width + local_x) * 3
                pixels.append(f"{rgb[pos]} {rgb[pos+1]} {rgb[pos+2]}")
        lines.append(" ".join(pixels))
    content = "\n".join(lines) + "\n"
    return content, {
        "format": "P3-PPM", "size": [canvas_width, canvas_height],
        "columns": columns, "rows": rows,
        "frame_ids": list(indices),
        "sha256": sha256(content.encode("utf-8")).hexdigest(),
    }


def _story_coverage(
    expected_world: str, frames: tuple[VisualFrame, ...],
    storyboard: object | None, anchors: Mapping[int, str] | None,
) -> dict:
    # Never infer a rendered cinematic from an unrelated procedural pixel array.
    if anchors is None:
        return {
            "authoritative_clip_attribution": False,
            "attributed_frames": 0,
            "clips_observed": [],
            "complete_storyboard_coverage": False,
        }
    from .game_frontier_expedition_cinematics import Storyboard
    if not isinstance(storyboard, Storyboard) or storyboard.world_digest != expected_world:
        raise ExpeditionError("post-production anchors lack source-bound storyboard")
    if not isinstance(anchors, Mapping):
        raise ExpeditionError("post-production clip anchors invalid")
    present = {f.frame for f in frames}
    clip_ids = {c.clip_id for c in storyboard.clips}
    if (any(type(k) is not int or k not in present or type(v) is not str
            or v not in clip_ids for k, v in anchors.items())
            or not anchors):
        raise ExpeditionError("post-production clip anchors reference missing frames")
    clips = sorted(set(anchors.values()))
    return {
        "authoritative_clip_attribution": False,  # caller annotations are not host attestations
        "attributed_frames": len(anchors),
        "clips_observed": clips,
        "complete_storyboard_coverage": len(clips) == len(clip_ids),
    }


def compile_frame_postproduction(
    frames: tuple[VisualFrame, ...], *, expected_world: str,
    policy: PostProductionPolicy = PostProductionPolicy(),
    storyboard: object | None = None,
    anchors: Mapping[int, str] | None = None,
) -> dict:
    """Execute all seven frame-production stages with replayable receipts.

    Stage 1 provenance; 2 exposure; 3 detail; 4 temporal stability;
    5 keyframes; 6 real PPM contact sheet; 7 clip annotations and replay.
    """
    source_kind = _validate(frames, expected_world, policy)
    spatial = [_spatial(f) for f in frames]
    temporal = [
        _temporal(a, b, policy) for a, b in zip(frames, frames[1:])
    ]
    selected = _select_frames(spatial, temporal, policy)
    ppm, mosaic = _sheet(frames, selected, policy)
    scenes = _story_coverage(expected_world, frames, storyboard, anchors)
    prior = _digest({"world": expected_world, "genesis": "postproduction.v1"})
    receipts = []
    for stat in spatial:
        payload = {"frame": stat["frame"], "source": stat["source_digest"],
                   "statistics": stat, "prior": prior}
        prior = _digest(payload)
        receipts.append({
            "frame": stat["frame"], "prior": payload["prior"], "receipt": prior,
        })
    findings = []
    if any(t["frozen"] for t in temporal):
        findings.append("frozen_or_unchanged_frame_interval")
    if any(t["frame_gap"] > 1 for t in temporal):
        findings.append("incomplete_frame_coverage")
    if any(s["shadow_fraction"] > .9 or s["highlight_fraction"] > .9 for s in spatial):
        findings.append("severely_clipped_exposure")
    if len(selected) < len(frames):
        findings.append("keyframe_subselection_only")
    report = {
        "schema": "skeleton.game.original_frame_postproduction.v1",
        "world": expected_world,
        "source_kind": source_kind,
        "input_frames": len(frames),
        "frame_span": [frames[0].frame, frames[-1].frame],
        "spatial": spatial, "temporal": temporal,
        "selected_keyframes": list(selected),
        "contact_sheet": mosaic,
        "story": scenes, "issues": findings,
        "journal": receipts, "receipt_head": prior,
        "native_renderer_attested": False,
        "audio_video_muxed": False,
        "model_training_performed": False,
        "production_publication_authorized": False,
    }
    report["receipt_digest"] = _digest(report)
    return {"report": report, "contact_sheet_ppm": ppm}


def verify_frame_postproduction(
    frames: tuple[VisualFrame, ...], submitted: Mapping, *,
    expected_world: str, policy: PostProductionPolicy = PostProductionPolicy(),
    storyboard: object | None = None,
    anchors: Mapping[int, str] | None = None,
) -> dict:
    if not isinstance(submitted, Mapping):
        raise ExpeditionError("post-production independent verification needs complete source")
    replay = compile_frame_postproduction(
        frames, expected_world=expected_world, policy=policy,
        storyboard=storyboard, anchors=anchors,
    )
    if dict(submitted) != replay:
        raise ExpeditionError("post-production bytes, decisions or receipts differ from source replay")
    return {
        "verified": True,
        "world": expected_world,
        "report_receipt": replay["report"]["receipt_digest"],
        "sheet_sha256": replay["report"]["contact_sheet"]["sha256"],
        "native_origin_attested": False,
    }
