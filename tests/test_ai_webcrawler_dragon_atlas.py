"""Stub for dragon atlas fixtures."""
from typing import Any

class DragonAtlasRegression:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass
    def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

def research_text(*args: Any, **kwargs: Any) -> str:
    return "stub research text"

def atlas_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "atlas": True}
