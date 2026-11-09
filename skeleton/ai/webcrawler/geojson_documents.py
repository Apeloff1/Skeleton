"""Finite GeoJSON research evidence with validated coordinates and geometry.

The parser does not draw maps, geocode, open external URLs, retain exact
device locations, or trust geometry as a navigation instruction. Geometry
summaries are coarsened and source-policy governed at the canonical worker.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

GEOJSON_MEDIA_TYPES = frozenset({"application/geo+json", "application/vnd.geo+json"})
_TYPES = frozenset({
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "GeometryCollection",
})
_KEYS = ("name", "title", "description", "category", "kind")
_MAX_VERTICES = 32768


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ResearchFormatError("duplicate GeoJSON property")
        obj[key] = value
    return obj


def _nonfinite(value: str) -> Any:
    raise ResearchFormatError("nonfinite GeoJSON coordinate")


@dataclass
class _ShapeBounds:
    count: int = 0
    west: float = 180.0
    south: float = 90.0
    east: float = -180.0
    north: float = -90.0

    def position(self, point: Any):
        if (not isinstance(point, list) or len(point) not in (2, 3)
                or any(type(v) not in (float, int) or not math.isfinite(v) for v in point)):
            raise ResearchFormatError("invalid GeoJSON coordinate tuple")
        lon, lat = point[0], point[1]
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ResearchFormatError("GeoJSON position outside WGS84")
        if len(point) == 3 and not -1e7 <= point[2] <= 1e7:
            raise ResearchFormatError("unbounded GeoJSON altitude")
        self.count += 1
        if self.count > _MAX_VERTICES:
            raise ResearchFormatError("GeoJSON geometry vertex budget exceeded")
        self.west = min(self.west, lon)
        self.east = max(self.east, lon)
        self.south = min(self.south, lat)
        self.north = max(self.north, lat)

    def summary(self) -> str:
        if not self.count:
            return "empty geometry"
        # Precision is reduced by design; this is advisory geometry evidence.
        return (
            f"vertices: {self.count}; bounds_approx: "
            f"{self.west:.2f},{self.south:.2f} to "
            f"{self.east:.2f},{self.north:.2f}"
        )


def _walk_geometry(value: Any, bounds: _ShapeBounds, depth: int = 0) -> str:
    if not isinstance(value, dict) or depth > 8:
        raise ResearchFormatError("invalid or overdeep GeoJSON geometry")
    kind = value.get("type")
    if not isinstance(kind, str) or kind not in _TYPES:
        raise ResearchFormatError("unsupported GeoJSON geometry kind")
    if kind == "GeometryCollection":
        geometries = value.get("geometries")
        if not isinstance(geometries, list) or len(geometries) > 128:
            raise ResearchFormatError("GeoJSON geometry collection capacity exceeded")
        for item in geometries:
            _walk_geometry(item, bounds, depth + 1)
        return kind
    coords = value.get("coordinates")
    if not isinstance(coords, list):
        raise ResearchFormatError("GeoJSON coordinates absent")
    if kind == "Point":
        bounds.position(coords)
        return kind
    stack = [(coords, 0)]
    nodes = 0
    while stack:
        value, level = stack.pop()
        nodes += 1
        if nodes > _MAX_VERTICES * 2 or level > 6 or not isinstance(value, list):
            raise ResearchFormatError("GeoJSON geometry nesting or node limit exceeded")
        if value and type(value[0]) in (float, int):
            bounds.position(value)
        elif len(value) <= _MAX_VERTICES:
            stack.extend((item, level + 1) for item in reversed(value))
        else:
            raise ResearchFormatError("GeoJSON vector fanout exceeded")
    return kind


def extract_geojson(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    try:
        doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, RecursionError) as exc:
        raise ResearchFormatError("invalid GeoJSON data") from exc
    if not isinstance(doc, dict):
        raise ResearchFormatError("GeoJSON root must be an object")
    root = doc.get("type")
    if root == "FeatureCollection":
        features = doc.get("features")
        if not isinstance(features, list) or not 1 <= len(features) <= 256:
            raise ResearchFormatError("GeoJSON feature collection capacity exceeded")
    elif root == "Feature":
        features = [doc]
    elif root in _TYPES:
        features = [{"type": "Feature", "geometry": doc, "properties": {}}]
    else:
        raise ResearchFormatError("unsupported GeoJSON root")
    result = []
    title = ""
    bounds = _ShapeBounds()
    for index, feature in enumerate(features, 1):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ResearchFormatError("invalid GeoJSON feature")
        geometry = feature.get("geometry")
        if geometry is None:
            raise ResearchFormatError("GeoJSON feature geometry absent")
        kind = _walk_geometry(geometry, bounds)
        attributes = feature.get("properties", {})
        if not isinstance(attributes, dict) or len(attributes) > 256:
            raise ResearchFormatError("invalid GeoJSON properties")
        labels = []
        for key in _KEYS:
            value = attributes.get(key)
            if isinstance(value, str) and 0 < len(value) <= 512:
                labels.append(f"{key}: {value}")
                if key in ("title", "name") and not title:
                    title = value
        result.append(f"GeoJSON feature {index}: geometry: {kind}; "
                      + "; ".join(labels or ["attributes: unprojected"]))
    result.append("Geometry summary: " + bounds.summary())
    return project_lines(result, title=title or "GeoJSON geometry", max_chars=max_chars)
