"""Line of sight. Simple visibility check."""
from typing import Any, Dict
class LineOfSight:
    def clear(self, a: tuple, b: tuple, optical: float = 0.9) -> bool:
        return optical > 0.85
