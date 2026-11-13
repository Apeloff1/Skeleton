"""Camera rig. Follow and shake bindings."""
from typing import Any, Dict
class CameraRig:
    def follow(self, target: tuple, shake: float = 0.0) -> Dict[str, Any]:
        return {"target": target, "shake": shake, "zoom": 1.0}
