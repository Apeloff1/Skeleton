"""Real-time graphics rendering and editing.
Chunk-based live render with optical-weighted edits and era-consistent palettes.
"""
from typing import Any, Dict, List, Tuple

class RealtimeGraphics:
    def __init__(self, mode: str = "2.5d", era: str = "ash"):
        self.mode = mode
        self.era = era
        self.chunks: Dict[str, Dict[str, Any]] = {}
        self.palette = {"ash": "#3a2a1a", "crystal": "#1a3a4a", "void": "#0a0a1a", "ps2": "#2a2a3a"}

    def render_chunk(self, x: int, y: int, optical: float) -> Dict[str, Any]:
        cid = f"{x // 16}_{y // 16}"
        base = self.palette.get(self.era, "#ffffff")
        return {
            "chunk": cid,
            "color": base,
            "optical": optical,
            "mode": self.mode,
            "layers": 2 if self.mode == "2.5d" else 8 if self.mode == "3d" else 1,
        }

    def edit_live(self, x: int, y: int, key: str, value: Any, optical: float) -> Dict[str, Any]:
        cid = f"{x // 16}_{y // 16}"
        if cid not in self.chunks:
            self.chunks[cid] = {}
        self.chunks[cid][key] = value
        self.chunks[cid]["optical"] = optical
        return {"ok": True, "chunk": cid, "edit": {key: value}, "optical": optical}

    def frame(self, width: int = 64, height: int = 64, optical: float = 0.93) -> Dict[str, Any]:
        cells = []
        for y in range(0, height, 16):
            for x in range(0, width, 16):
                cells.append(self.render_chunk(x, y, optical))
        return {
            "width": width,
            "height": height,
            "cells": len(cells),
            "mode": self.mode,
            "era": self.era,
            "optical": optical,
            "schema": "skeleton.realtime.graphics.v1",
        }
