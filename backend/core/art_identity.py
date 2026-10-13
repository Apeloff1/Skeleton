"""Art identity pass for forge → Godot materialise.

Loads design/art/visual_identity_tokens.json (or an embedded fallback),
injects lighting + material metadata into scene payloads, and critiques
whether a Godot .tscn text is silhouette/read/consistency ready.

Extend-only. Does not replace forge_quality fidelity floats — those are
not an art language.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TOKEN_REL = Path("design") / "art" / "visual_identity_tokens.json"
_REPO_MARKERS = (Path("design"), Path("backend"), Path("README.md"))

# Embedded fallback so tests/CI work even if the JSON path is unresolved.
_FALLBACK_TOKENS: dict[str, Any] = {
    "version": 1,
    "colors": {
        "surface": "#0A0A0A",
        "onSurface": "#E5E5E5",
        "surfaceSecondary": "#141414",
        "surfaceTertiary": "#1F1F1F",
        "brand": "#8B5CF6",
        "brandSecondary": "#A78BFA",
        "brandTertiary": "#2E1B5B",
        "success": "#10B981",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "info": "#3B82F6",
        "border": "#262626",
        "borderStrong": "#404040",
    },
    "lighting": {
        "key": {"type": "DirectionalLight2D", "energy": 1.15, "color": "#E5E5E5", "rotation_deg": -35},
        "fill": {"type": "DirectionalLight2D", "energy": 0.45, "color": "#A78BFA", "rotation_deg": 140},
        "rim": {"type": "PointLight2D", "energy": 0.85, "color": "#8B5CF6", "texture_scale": 2.4},
    },
    "materials": {
        "body": {"albedo": "#1F1F1F", "metallic": 0.15, "roughness": 0.55},
        "accent": {"albedo": "#8B5CF6", "emission": "#8B5CF6", "emission_energy": 0.6},
        "ground": {"albedo": "#141414", "metallic": 0.05, "roughness": 0.8},
        "player": {"albedo": "#2E1B5B", "emission": "#A78BFA", "emission_energy": 0.35},
    },
    "silhouette": {
        "required_nodes": ["Player", "Ground", "Camera2D"],
        "min_collision_extents": [8, 8],
        "reject_bare_node2d_only": True,
    },
}

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
_NODE_RE = re.compile(r'^\[node name="([^"]+)" type="([^"]+)"', re.M)
_LIGHT_TYPES = frozenset({"DirectionalLight2D", "PointLight2D", "OmniLight3D", "DirectionalLight3D"})


def _find_repo_root(start: Path | None = None) -> Path | None:
    cur = (start or Path(__file__)).resolve()
    for _ in range(8):
        if all((cur / m).exists() for m in _REPO_MARKERS):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_tokens(path: Path | str | None = None) -> dict[str, Any]:
    """Load visual identity tokens; fall back to embedded set."""
    if path is not None:
        p = Path(path)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    root = _find_repo_root()
    if root is not None:
        p = root / _TOKEN_REL
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return dict(_FALLBACK_TOKENS)


def palette_hexes(tokens: dict[str, Any] | None = None) -> set[str]:
    toks = tokens or load_tokens()
    colors = toks.get("colors") or {}
    mats = toks.get("materials") or {}
    hexes = {str(v).upper() for v in colors.values() if isinstance(v, str)}
    for mat in mats.values():
        if not isinstance(mat, dict):
            continue
        for key in ("albedo", "emission"):
            v = mat.get(key)
            if isinstance(v, str):
                hexes.add(v.upper())
    lights = toks.get("lighting") or {}
    for light in lights.values():
        if isinstance(light, dict) and isinstance(light.get("color"), str):
            hexes.add(light["color"].upper())
    return hexes


def apply_art_pass(scene_text: str, *, template: str = "empty",
                   tokens: dict[str, Any] | None = None) -> str:
    """Inject lighting + materialised Player/Ground mods into Godot .tscn text.

    Idempotent: if an ArtIdentityMarker comment is already present, return
    the text unchanged. Extends bare Node2D scaffolds so silhouette/read
    critique can pass.
    """
    if not scene_text or "ArtIdentityMarker" in scene_text:
        return scene_text
    toks = tokens or load_tokens()
    mats = toks.get("materials") or {}
    lights = toks.get("lighting") or {}
    player_mat = mats.get("player") or {}
    ground_mat = mats.get("ground") or {}
    key = lights.get("key") or {}
    fill = lights.get("fill") or {}
    rim = lights.get("rim") or {}

    # Bump load_steps in header when we add resources (best-effort).
    out = scene_text
    out = re.sub(
        r"load_steps=(\d+)",
        lambda m: f"load_steps={int(m.group(1)) + 3}",
        out,
        count=1,
    )

    # Annotate Main with art identity marker.
    out = out.replace(
        '[node name="Main" type="Node2D"]',
        '[node name="Main" type="Node2D"]\n'
        '# ArtIdentityMarker visual_identity_tokens v'
        f'{toks.get("version", 1)} template={template}',
        1,
    )

    # Player materialise: modulate + emission-ish via modulate + z_index.
    player_mod = player_mat.get("albedo", "#2E1B5B")
    player_em = player_mat.get("emission", "#A78BFA")
    out = out.replace(
        '[node name="Player" type="CharacterBody2D" parent="."]',
        '[node name="Player" type="CharacterBody2D" parent="."]\n'
        f'modulate = Color("{player_mod}")\n'
        f'# material.emission {player_em} energy={player_mat.get("emission_energy", 0.35)}',
        1,
    )

    # Ground materialise.
    ground_mod = ground_mat.get("albedo", "#141414")
    if '[node name="Ground" type="StaticBody2D" parent="."]' in out:
        out = out.replace(
            '[node name="Ground" type="StaticBody2D" parent="."]',
            '[node name="Ground" type="StaticBody2D" parent="."]\n'
            f'modulate = Color("{ground_mod}")',
            1,
        )

    # Lighting block under Main.
    light_block = "\n".join([
        '',
        '[node name="ArtKeyLight" type="'
        f'{key.get("type", "DirectionalLight2D")}" parent="Main"]',
        f'energy = {key.get("energy", 1.15)}',
        f'color = Color("{key.get("color", "#E5E5E5")}")',
        f'rotation_degrees = {key.get("rotation_deg", -35)}',
        '',
        '[node name="ArtFillLight" type="'
        f'{fill.get("type", "DirectionalLight2D")}" parent="Main"]',
        f'energy = {fill.get("energy", 0.45)}',
        f'color = Color("{fill.get("color", "#A78BFA")}")',
        f'rotation_degrees = {fill.get("rotation_deg", 140)}',
        '',
        '[node name="ArtRimLight" type="'
        f'{rim.get("type", "PointLight2D")}" parent="Main"]',
        f'energy = {rim.get("energy", 0.85)}',
        f'color = Color("{rim.get("color", "#8B5CF6")}")',
        f'texture_scale = {rim.get("texture_scale", 2.4)}',
        '',
    ])
    return out.rstrip() + "\n" + light_block


def critique(scene_text: str, *, tokens: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic art critique: silhouette / readable / consistent."""
    toks = tokens or load_tokens()
    fails: list[str] = []
    sil = toks.get("silhouette") or {}
    required = list(sil.get("required_nodes") or ["Player", "Ground", "Camera2D"])

    nodes = {name: typ for name, typ in _NODE_RE.findall(scene_text or "")}
    for name in required:
        if name not in nodes:
            fails.append(f"silhouette: missing node {name}")

    if sil.get("reject_bare_node2d_only") and list(nodes.values()) == ["Node2D"]:
        fails.append("silhouette: bare Node2D-only scene")

    has_light = any(t in _LIGHT_TYPES for t in nodes.values())
    has_light = has_light or bool(re.search(r'type="(DirectionalLight2D|PointLight2D|OmniLight3D)"', scene_text or ""))
    if not has_light:
        fails.append("readable: no key/rim lighting")

    palette = palette_hexes(toks)
    for hx in _HEX_RE.findall(scene_text or ""):
        if hx.upper() not in palette:
            fails.append(f"consistent: off-palette color {hx}")
            break

    return {
        "silhouette_ok": not any(f.startswith("silhouette") for f in fails),
        "readable": not any(f.startswith("readable") for f in fails),
        "consistent": not any(f.startswith("consistent") for f in fails),
        "passed": len(fails) == 0,
        "fails": fails,
    }


def art_ready(scene_text: str, *, tokens: dict[str, Any] | None = None) -> bool:
    return bool(critique(scene_text, tokens=tokens).get("passed"))
