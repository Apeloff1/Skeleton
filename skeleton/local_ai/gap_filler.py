"""
Gap Filler. Dynamically registers all seam_XXX modules into the operational engine.
Makes the full set of seams functional and callable.
"""
import importlib
from typing import Dict, Callable
from .local_ai_index import SEAMS

class GapFiller:
    def __init__(self):
        self.seams: Dict[str, Callable] = {}
        self._load_core()
        self._load_numbered()

    def _load_core(self):
        for name in SEAMS:
            try:
                mod = importlib.import_module(f"skeleton.local_ai.{name}")
                if hasattr(mod, "process"):
                    self.seams[name] = mod.process
            except Exception:
                pass

    def _load_numbered(self):
        for i in range(200):
            name = f"seam_{i:03d}"
            try:
                mod = importlib.import_module(f"skeleton.local_ai.{name}")
                func = getattr(mod, f"process_{i}", None)
                if func:
                    self.seams[name] = func
            except Exception:
                continue

    def call(self, name: str, data: dict) -> dict:
        if name in self.seams:
            return self.seams[name](data)
        return {"error": "seam not found", "name": name}

    def list(self) -> list:
        return list(self.seams.keys())
