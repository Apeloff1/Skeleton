"""Bounded, non-rendering SVG shape and canvas inventory.

DTD/ENTITY, scripts, foreignObject, event attributes and unsupported element
counts fail closed. No fonts, remote images, stylesheets, URLs, SVG SMIL
animations or JavaScript are resolved. Vector geometry remains unreviewed.
"""
from __future__ import annotations

from collections import Counter
import math
import re
import xml.etree.ElementTree as ET

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

SVG_TYPES=frozenset({"image/svg+xml"})
_SHAPES=frozenset({
    "path","rect","circle","ellipse","line","polyline","polygon",
    "text","use","image",
})
_FORBIDDEN=re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b",re.I)
_RESTRICTED=frozenset(("script","foreignObject","iframe","animate","animateMotion",
                       "animateTransform","set"))
_MAX_ELEMENTS=16384
_MAX_DEPTH=32


def _tag(tag:str)->str:
    return tag.rsplit("}",1)[-1] if "}" in tag else tag


def _dimension(value:object)->str:
    if not isinstance(value,str) or len(value)>48:
        return "unspecified"
    match=re.fullmatch(r"([0-9]{1,7}(?:\.[0-9]{1,5})?)(?:px)?",value.strip())
    if match and 0<float(match.group(1))<=16384:
        return match.group(1)
    return "unspecified"


def extract_svg(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    if _FORBIDDEN.search(raw) or len(raw)>1_048_576:
        raise ResearchFormatError("SVG active DTD/entity or size constraint")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,RecursionError) as exc:
        raise ResearchFormatError("unparseable SVG XML") from exc
    if _tag(root.tag)!="svg":
        raise ResearchFormatError("SVG root element missing")
    counts=Counter()
    visited=0
    stack=[(root,1)]
    while stack:
        node,depth=stack.pop()
        visited+=1
        if visited>_MAX_ELEMENTS or depth>_MAX_DEPTH:
            raise ResearchFormatError("SVG element or depth cap exceeded")
        name=_tag(node.tag)
        if name in _RESTRICTED:
            raise ResearchFormatError("SVG active or foreign content denied")
        for key,value in node.attrib.items():
            label=_tag(key).lower()
            if label.startswith("on"):
                raise ResearchFormatError("SVG event handler attribute denied")
            if not isinstance(value,str) or len(value)>8192:
                raise ResearchFormatError("SVG attribute bound exceeded")
        if name in _SHAPES:
            counts[name]+=1
        stack.extend((child,depth+1) for child in node)
    view_box=root.attrib.get("viewBox","")
    dimensions="unspecified"
    if view_box:
        fields=view_box.replace(","," ").split()
        if len(fields)!=4:
            raise ResearchFormatError("invalid SVG viewBox dimension count")
        try:
            numbers=[float(x) for x in fields]
        except ValueError as exc:
            raise ResearchFormatError("invalid SVG viewBox") from exc
        if any(not math.isfinite(x) or abs(x)>1e7 for x in numbers):
            raise ResearchFormatError("SVG viewBox extent exceeded")
        if not 0<numbers[2]<=1e7 or not 0<numbers[3]<=1e7:
            raise ResearchFormatError("invalid SVG viewBox size")
        dimensions=", ".join(f"{x:.2f}" for x in numbers)
    lines=[
        "Vector asset: SVG shape inventory; unreviewed",
        f"Canvas width: {_dimension(root.attrib.get('width'))}; "
        f"height: {_dimension(root.attrib.get('height'))}",
        f"ViewBox approximate: {dimensions}",
        f"XML elements: {visited}; vector shapes: {sum(counts.values())}",
    ]
    lines.extend(f"Vector primitive {kind}: {counts[kind]}" for kind in sorted(counts))
    lines.append("Scripts, URL references, imagery and fonts: not loaded or executed")
    return project_lines(lines,title="SVG vector inventory",max_chars=max_chars)
