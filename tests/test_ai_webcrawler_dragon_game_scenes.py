"""Dragon game scenes fixtures."""
from typing import Any

GODOT = "application/x-godot-scene"
UNITY = "application/x-unity-scene"
USDA = "model/vnd.usda"
LDRAW = "application/x-ldraw"

def game_scene(data: bytes = b"", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "type": "game_scene", "size": len(data)}
