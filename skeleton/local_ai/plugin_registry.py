"""
Operational Plugin Registry. Register and invoke extension seams at runtime.
Fills the extensibility gap. Extend-only.
"""
from typing import Dict, Callable

class PluginRegistry:
    def __init__(self):
        self.plugins: Dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self.plugins[name] = fn

    def invoke(self, name: str, data: dict) -> dict:
        if name in self.plugins:
            return self.plugins[name](data)
        return {"error": "plugin not found"}

    def list(self) -> list:
        return list(self.plugins.keys())
