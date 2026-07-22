"""
╔════════════════════════════════════════════════════════════════════════╗
║  BUILD CONFIG — the Galaxy-Builder Advanced choices, made to matter.    ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Normalises every advanced choice/setting (graphic/sound/music/design/  ║
║  cinematic/director style, dimension, asset & model style, plus the     ║
║  production sliders: texture res, poly count, shader, particles, audio  ║
║  layering, accessibility …) into a canonical config + a flat "applied   ║
║  choices" stamp that is folded into EVERY forged item and asset, so the ║
║  gates can prove each choice is reflected in every step of the snowball. ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Any

# (key, label, kind, target) — the canonical set of choices that must matter.
# kind: "style" = enum pick · "slider" = 0-100 · "flag" = on/off
# target: which forge output the choice shapes.
CHOICE_SPECS: list[tuple[str, str, str, str]] = [
    ("graphic_style", "Graphic Style", "style", "visual"),
    ("design_style", "Design Style", "style", "visual"),
    ("cinematic_style", "Cinematic Style", "style", "visual"),
    ("director_style", "Director Style", "style", "meta"),
    ("dimension", "Dimension", "style", "geometry"),
    ("asset_style", "Asset Style", "style", "visual"),
    ("model_style", "Model Style", "style", "geometry"),
    ("sound_style", "Sound Style", "style", "audio"),
    ("music_style", "Music Style", "style", "audio"),
    ("texture_resolution", "Texture Resolution", "slider", "visual"),
    ("model_poly_count", "Model Poly Count", "slider", "geometry"),
    ("shader_complexity", "Shader Complexity", "slider", "visual"),
    ("particle_density", "Particle Density", "slider", "visual"),
    ("music_variety", "Music Variety", "slider", "audio"),
    ("sfx_layering", "SFX Layering", "slider", "audio"),
    ("voice_acting_depth", "Voice-Acting Depth", "slider", "audio"),
    ("difficulty_assist", "Difficulty Assist", "slider", "gameplay"),
]

# Merge in the genuine spec-aware axis catalog (snowball_axes) so every new
# advanced axis is a first-class choice the gates + awareness count. The thin
# original entries above are kept for back-compat; axis keys win on conflict.
try:
    from core import snowball_axes as _axes
    _existing = {k for k, *_ in CHOICE_SPECS}
    for _a in _axes.AXES:
        if _a["key"] not in _existing:
            CHOICE_SPECS.append((_a["key"], _a["label"], _a["kind"], _a["target"]))
            _existing.add(_a["key"])
except Exception:  # pragma: no cover - catalog optional
    _axes = None  # type: ignore

_SPEC_BY_KEY = {k: (label, kind, target) for k, label, kind, target in CHOICE_SPECS}

_TIERS = ["none", "low", "medium", "high", "ultra"]


def _tier(v: Any) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "medium"
    return _TIERS[min(len(_TIERS) - 1, max(0, n // 21))]  # 0-100 → 5 tiers


def normalize(raw: dict | None) -> dict:
    """Collect the advanced choices from a (possibly nested) payload into one
    flat canonical config. Accepts styles + sliders + extra_params merged."""
    raw = raw or {}
    flat: dict[str, Any] = {}
    # merge nested buckets the factory sends
    for bucket in ("styles", "sliders", "extra_params", "production", "config"):
        b = raw.get(bucket)
        if isinstance(b, dict):
            flat.update(b)
    flat.update({k: v for k, v in raw.items() if not isinstance(v, dict)})
    out: dict[str, Any] = {}
    for key, _label, _kind, _target in CHOICE_SPECS:
        if key in flat and flat[key] not in (None, ""):
            out[key] = flat[key]
    return out


def derive(config: dict) -> dict:
    """Flatten config into the per-asset/item stamp (string-valued)."""
    stamp: dict[str, str] = {}
    for key, _label, kind, _target in CHOICE_SPECS:
        if key not in config:
            continue
        v = config[key]
        stamp[key] = _tier(v) if kind == "slider" else str(v)
    return stamp


def dimension_is_2d(config: dict) -> bool:
    d = str(config.get("dimension", "")).lower()
    return d in ("2d", "two_d", "2", "pixel", "side_2d", "topdown_2d")


def texture_tier(config: dict) -> str:
    return _tier(config.get("texture_resolution", 50))


def poly_tier(config: dict) -> str:
    return _tier(config.get("model_poly_count", 50))


def summary(config: dict) -> dict:
    """Human-readable rollup of the locked advanced choices."""
    return {
        "count": len(config),
        "choices": [
            {"key": k, "label": _SPEC_BY_KEY[k][0],
             "kind": _SPEC_BY_KEY[k][1], "target": _SPEC_BY_KEY[k][2],
             "value": config[k]}
            for k in config if k in _SPEC_BY_KEY
        ],
    }
