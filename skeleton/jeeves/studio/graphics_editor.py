"""Graphics editor with learning and chunk consistency.
Supports on-the-fly edits that stay consistent via chunking.
"""
from typing import Any, Dict, List

class GraphicsEditor:
    def __init__(self):
        self.chunks: Dict[str, Dict[str, Any]] = {}
        self.learned: List[Dict[str, Any]] = []

    def chunk_id(self, x: int, y: int, size: int = 16) -> str:
        return f"{x // size}_{y // size}"

    def edit(self, x: int, y: int, key: str, value: Any) -> Dict[str, Any]:
        cid = self.chunk_id(x, y)
        if cid not in self.chunks:
            self.chunks[cid] = {}
        self.chunks[cid][key] = value
        self.learned.append({"chunk": cid, "key": key, "value": value})
        return {"ok": True, "chunk": cid, "edit": {key: value}}

    def batch_edit(self, edits: List[Dict[str, Any]], optical: float) -> Dict[str, Any]:
        results = []
        for e in edits:
            results.append(self.edit(e["x"], e["y"], e["key"], e["value"]))
        self.learn_from(optical)
        return {"applied": len(results), "optical": optical}

    def learn_from(self, optical: float) -> Dict[str, Any]:
        if optical > 0.9 and self.learned:
            pattern = self.learned[-1]
            return {"learned": True, "pattern": pattern, "optical": optical}
        return {"learned": False}

    def consistent(self, cid: str) -> bool:
        return cid in self.chunks and len(self.chunks[cid]) > 0

    def status(self) -> Dict[str, Any]:
        return {
            "chunks": len(self.chunks),
            "learned": len(self.learned),
            "schema": "skeleton.graphics_editor.v1",
        }
