"""Deterministic original vector environment illustrations from authored palettes.

This renders real standalone SVG bytes without network assets or copying any
existing art.  It is a lightweight original production asset, not a complete
native 2D/3D world or commercially-qualified art pipeline.
"""
from __future__ import annotations

from hashlib import sha256
from math import cos, pi, sin
import re
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
VIEW_WIDTH = 1280
VIEW_HEIGHT = 720


def _element(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    return ET.SubElement(parent, f"{{{SVG}}}{tag}",
                         {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def _stable(seed: bytes, *parts: int) -> float:
    index = b":".join(str(p).encode("ascii") for p in parts)
    return int.from_bytes(sha256(seed + b"/" + index).digest()[:8], "big") / 2**64


def render_environment_svg(documents: Mapping[str, Any]) -> bytes:
    program = compile_quest_program(documents)
    visual = documents.get("visual")
    narrative = documents.get("narrative")
    if (not isinstance(visual, dict) or not isinstance(narrative, dict)
            or visual.get("project_id") != program.project_id
            or visual.get("release_certified") is not False):
        raise StudioQuestError("unqualified or mismatched original art documents")
    direction = visual.get("art_direction")
    palette = direction.get("palette") if isinstance(direction, dict) else None
    if (not isinstance(palette, list) or len(palette) < 3
            or len(palette) > 8 or any(
                not isinstance(c, str) or not COLOUR.fullmatch(c) for c in palette
            )):
        raise StudioQuestError("authored vector palette missing or invalid")
    seed = sha256((program.source_digest + program.project_id
                   + ":original-vector-environment:v1").encode("ascii")).digest()
    name = narrative.get("title", program.project_id)
    if not isinstance(name, str) or len(name) > 256:
        raise StudioQuestError("invalid environment title")

    root = ET.Element(f"{{{SVG}}}svg", {
        "viewBox": f"0 0 {VIEW_WIDTH} {VIEW_HEIGHT}",
        "width": str(VIEW_WIDTH), "height": str(VIEW_HEIGHT),
        "role": "img", "aria-label": name,
    })
    _element(root, "title").text = name
    defs = _element(root, "defs")
    background = _element(defs, "linearGradient", id="sky", x1="0", y1="0", x2="0", y2="1")
    for offset, color in (("0%", palette[0]), ("62%", palette[1]),
                          ("100%", palette[2])):
        _element(background, "stop", offset=offset, stop_color=color)
    _element(root, "rect", width=VIEW_WIDTH, height=VIEW_HEIGHT, fill="url(#sky)")
    haze = _element(root, "g", fill=palette[-1], fill_opacity="0.42")
    for i in range(36):
        x = int(_stable(seed, 3, i) * VIEW_WIDTH)
        y = int(_stable(seed, 4, i) * 360)
        radius = 1 + int(_stable(seed, 5, i) * 3)
        _element(haze, "circle", cx=x, cy=y, r=radius)
    for depth in range(7):
        horizon = 265 + depth * 57
        layer = _element(root, "g", opacity=f"{0.39 + depth * 0.095:.3f}")
        points = [f"0,{VIEW_HEIGHT}", f"0,{horizon}"]
        for index in range(1, 33):
            x = round(index * VIEW_WIDTH / 32)
            wave = sin((index / 5 + depth) * pi) * (36 - depth * 3)
            irregular = (_stable(seed, depth, index) - 0.5) * (90 - depth * 9)
            y = max(55, min(VIEW_HEIGHT, round(horizon + wave + irregular)))
            points.append(f"{x},{y}")
        points.append(f"{VIEW_WIDTH},{VIEW_HEIGHT}")
        _element(layer, "polygon", points=" ".join(points),
                 fill=palette[min(depth // 2, len(palette) - 1)])
    # Foreground consists of geometric original environmental forms, not
    # externally sourced meshes or textures.
    foreground = _element(root, "g", fill=palette[-1], fill_opacity="0.64")
    for i in range(21):
        x = int(_stable(seed, 8, i) * VIEW_WIDTH)
        y = 490 + int(_stable(seed, 9, i) * 210)
        height = 12 + int(_stable(seed, 10, i) * 38)
        width = 3 + int(_stable(seed, 11, i) * 12)
        _element(foreground, "path", d=(
            f"M{x} {y} L{x-width} {y+height} L{x+width} {y+height} Z"
        ))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def vector_art_receipt(documents: Mapping[str, Any]) -> dict[str, object]:
    payload = render_environment_svg(documents)
    program = compile_quest_program(documents)
    return {"schema": "skeleton.game_builder.original_environment_svg.v1",
            "project_id": program.project_id,
            "svg_sha256": sha256(payload).hexdigest(),
            "svg_bytes": len(payload), "width": VIEW_WIDTH, "height": VIEW_HEIGHT,
            "original_asset_rendered": True, "native_world_rendered": False,
            "rights_independently_qualified": False, "release_certified": False}
