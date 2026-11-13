"""Key crate. Contains key items."""
from typing import Any, Dict
class KeyCrate:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "key_crate", "optical": kwargs.get("optical", 0.9)}
