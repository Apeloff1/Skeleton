"""Blueprint materialisers — target output formats (JSON/YAML).

Forge.materialise() emits dict; Materialiser converts back to bytes
for file/stream output and chooses format by name with helper
materialiser_for("yaml") style. Lightweight pyyaml fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from skeleton.kernel.errors import MaterialisationError

def _encode_godot(d):
    files = d.get("files") or {}
    if not files:
        from skeleton.forge.godot_emit import emit_godot
        files = emit_godot(d.get("pack") or {}, title=str(d.get("name") or "FORGE"))
    manifest = {path: ("gd" if path.endswith(".gd") else "other") for path in files}
    payload = {"manifest": manifest, "files": files, "count": len(files)}
    return json.dumps(payload, indent=2).encode()



try:
    import yaml as _yaml  # PyYAML
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass(frozen=True)
class Materialiser:
    name: str
    encode: Callable[[Dict[str, Any]], bytes]


class MaterialisationRegistry:
    """Pluggable materialisers: json built-in, yaml with PyYAML."""

    def __init__(self) -> None:
        self._materialisers = {
            "json": Materialiser(
                name="json",
                encode=lambda d: json.dumps(d, indent=2).encode(),
            )
        }
        if HAS_YAML:
            self._materialisers["yaml"] = Materialiser(
                name="yaml",
                encode=lambda d: _yaml.safe_dump(d, sort_keys=False).encode(),
            )
        self._materialisers["godot"] = Materialiser(
            name="godot",
            encode=_encode_godot,
        )

    def get(self, name: str) -> Materialiser:
        materialiser = self._materialisers.get(name)
        if materialiser is None:
            raise MaterialisationError(
                "unknown materialiser",
                context={"name": name, "known": list(self._materialisers)},
            )
        return materialiser

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._materialisers))
