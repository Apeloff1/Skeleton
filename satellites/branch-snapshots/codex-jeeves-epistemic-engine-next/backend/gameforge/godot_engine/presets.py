"""presets.py — export_presets.cfg generation for scaffolded projects.

Covers Linux, Windows, macOS, and Web so `export` jobs work out of the box.
"""
from __future__ import annotations

_PLATFORMS = [
    ("Linux/X11", "linuxbsd", "x86_64", "game.x86_64"),
    ("Windows Desktop", "windows", "x86_64", "game.exe"),
    ("macOS", "macos", "universal", "game.zip"),
    ("Web", "web", "", "game.html"),
]


def render_export_presets(project_name: str) -> str:
    parts: list[str] = []
    for i, (label, platform, arch, out) in enumerate(_PLATFORMS):
        parts.append(f"""[preset.{i}]

name="{label}"
platform="{platform}"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="builds/{out}"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.{i}.options]

custom_template/debug=""
custom_template/release=""
variant/export_type=0
""")
    return "\n".join(parts)


def preset_names() -> list[str]:
    return [p[0] for p in _PLATFORMS]
