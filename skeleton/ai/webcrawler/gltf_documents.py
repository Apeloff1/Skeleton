"""Finite glTF 2.0 JSON scene graph inventory, no external buffer loading.

The graph is scanned as inert source evidence: no renderers, URI fetches,
shader code, embedded data buffers, material files or animations run.
"""
from __future__ import annotations

import json
from typing import Any

from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

GLTF_MEDIA_TYPES = frozenset({"model/gltf+json", "application/x-gltf+json"})


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for k,v in pairs:
        if k in obj:
            raise ResearchFormatError("duplicate glTF JSON property")
        obj[k] = v
    return obj


def _reject(value: str) -> Any:
    raise ResearchFormatError("glTF nonfinite JSON constant")


def _bounded_list(doc: dict, key: str, maximum: int) -> list:
    rows = doc.get(key, [])
    if not isinstance(rows, list) or len(rows) > maximum:
        raise ResearchFormatError("glTF array capacity invalid")
    return rows


def _index(value: object, length: int) -> int:
    if type(value) is not int or not 0 <= value < length:
        raise ResearchFormatError("glTF graph reference out of bounds")
    return value


def extract_gltf(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject)
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid glTF JSON source") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("asset"), dict):
        raise ResearchFormatError("glTF asset envelope absent")
    if doc["asset"].get("version") != "2.0":
        raise ResearchFormatError("only glTF 2.0 is supported")
    nodes = _bounded_list(doc, "nodes", 1024)
    meshes = _bounded_list(doc, "meshes", 512)
    scenes = _bounded_list(doc, "scenes", 64)
    animations = _bounded_list(doc, "animations", 256)
    materials = _bounded_list(doc, "materials", 256)
    buffers = _bounded_list(doc, "buffers", 256)
    images = _bounded_list(doc, "images", 256)
    children: list[list[int]] = []
    for node in nodes:
        if not isinstance(node, dict):
            raise ResearchFormatError("invalid glTF node")
        links = node.get("children", [])
        if not isinstance(links, list) or len(links) > 128:
            raise ResearchFormatError("glTF node children exceed bound")
        outgoing = [_index(v, len(nodes)) for v in links]
        if len(set(outgoing)) != len(outgoing):
            raise ResearchFormatError("duplicate glTF child identity")
        children.append(outgoing)
        if "mesh" in node:
            _index(node["mesh"], len(meshes))
    roots = []
    for scene in scenes:
        if not isinstance(scene, dict) or not isinstance(scene.get("nodes", []), list):
            raise ResearchFormatError("glTF scene roots invalid")
        for root in scene.get("nodes", []):
            roots.append(_index(root, len(nodes)))
    # Three-color iterative DFS detects cycles without recursive traversal.
    colors = [0] * len(nodes)
    edges = 0
    for initial in range(len(nodes)):
        if colors[initial]:
            continue
        colors[initial] = 1
        stack = [(initial, 0)]
        while stack:
            node, i = stack[-1]
            if i >= len(children[node]):
                colors[node] = 2
                stack.pop()
                continue
            child = children[node][i]
            stack[-1] = (node, i+1)
            edges += 1
            if edges > 8192 or colors[child] == 1:
                raise ResearchFormatError("cyclic or oversized glTF scene graph")
            if colors[child] == 0:
                colors[child] = 1
                stack.append((child,0))
    for array in (meshes, animations, materials, buffers, images):
        if any(not isinstance(item, dict) for item in array):
            raise ResearchFormatError("malformed glTF asset catalog element")
    # Even if buffers contain URI or base64 data, no bytes are decoded.
    external = sum(bool(item.get("uri")) for item in buffers + images)
    labels = [
        "3D asset: glTF 2.0 scene graph",
        f"Scenes: {len(scenes)}; scene roots: {len(roots)}",
        f"Nodes: {len(nodes)}; graph edges: {edges}; meshes: {len(meshes)}",
        f"Materials: {len(materials)}; animations: {len(animations)}",
        f"Buffers: {len(buffers)}; images: {len(images)}",
        f"External or embedded URI references declared: {external} (not fetched)",
    ]
    names = []
    for source in meshes:
        name = source.get("name")
        if isinstance(name, str) and 0 < len(name) <= 128 and len(names) < 32:
            names.append(name)
    if names:
        labels.append("Named meshes: " + "; ".join(names))
    return project_lines(labels, title="glTF scene inventory", max_chars=max_chars)
