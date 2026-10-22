"""skeleton/security/vault_path_wiring.py
Example fail-closed vault path wiring that routes every open through the hardener.
No direct user-path use. Complements decoded_path.py.
"""
from __future__ import annotations

from pathlib import Path

from skeleton.security.path_url_hardener import harden_path, PathHardeningError

def vault_open(user_path: str, root: Path, mode: str = "rb") -> bytes:
    """Harden then open. Raises PathHardeningError on any escape or invalid path."""
    try:
        safe = harden_path(user_path, root=root)
        with open(safe, mode) as fh:
            return fh.read()
    except (OSError, PathHardeningError) as exc:
        raise PathHardeningError(f"vault open failed: {exc}") from exc

def vault_list(root: Path) -> list[str]:
    """List only after confirming root is hardened."""
    safe_root = harden_path(".", root=root)
    return [p.name for p in safe_root.iterdir() if p.is_file()]
