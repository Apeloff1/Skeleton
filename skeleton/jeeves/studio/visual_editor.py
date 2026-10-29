"""Visual editor.
Chunk-based visual editing with optical learning and era-consistent palettes.
"""
from typing import Any, Dict, List

class VisualEditor:
    def __init__(self):
        self.layers: Dict[str, Dict[str, Any]] = {"base": {}, "overlay": {}, "fx": {}}
        self.palette = {"ash": "#3a2a1a", "crystal": "#1a3a4a", "void": "#0a0a1a"}

    def paint(self, layer: str, chunk: str, color: str, optical: float) -> Dict[str, Any]:
        if layer not in self.layers:
            self.layers[layer] = {}
        self.layers[layer][chunk] = {"color": color, "optical": optical}
        return {"ok": True, "layer": layer, "chunk": chunk}

    def era_palette(self, era: str) -> str:
        return self.palette.get(era, "#ffffff")

    def status(self) -> Dict[str, Any]:
        return {"layers": list(self.layers), "painted": sum(len(v) for v in self.layers.values())}
