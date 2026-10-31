"""Secret area. Optical-gated hidden rooms."""
from typing import Any, Dict
class SecretArea:
    def reveal(self, optical: float) -> bool:
        return optical > 0.93
