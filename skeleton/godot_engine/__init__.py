"""skeleton.godot_engine — artifact-plane alias onto gameforge.godot_engine.binary."""
from __future__ import annotations

try:
    from gameforge.godot_engine.binary import locate, binary_status, get_binary
except ImportError:  # backend not on path — local stub
    from skeleton.godot_engine.binary import locate, binary_status, get_binary

__all__ = ["locate", "binary_status", "get_binary"]
